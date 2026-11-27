"""Process-group runner (backend copy, ruling R20): real children, real timeouts."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from snowbot.backends.proc import TIMEOUT_RETURNCODE, run_killing_group

# Starts a grandchild sleeper, records both pids, prints, then sleeps past the timeout.
SPAWNER = """\
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
open(sys.argv[1], "w").write(f"{child.pid}\\n")
print("started", flush=True)
time.sleep(60)
"""

# Leaves a background sleeper (with its output redirected) behind and exits at once.
LEAVER = """\
import subprocess, sys
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
open(sys.argv[1], "w").write(f"{child.pid}\\n")
print("bye")
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone_soon(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_normal_exit(tmp_path: Path) -> None:
    proc = run_killing_group(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        cwd=tmp_path,
        env=None,
        timeout=30,
    )
    assert proc.returncode == 0 and proc.stdout == "out\n" and proc.stderr == "err\n"


def test_exit_code_passed_through(tmp_path: Path) -> None:
    proc = run_killing_group(
        [sys.executable, "-c", "raise SystemExit(4)"], cwd=tmp_path, env={}, timeout=30
    )
    assert proc.returncode == 4


def test_timeout_kills_whole_group(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    start = time.monotonic()
    proc = run_killing_group(
        [sys.executable, "-c", SPAWNER, str(pidfile)],
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=1.5,
    )
    assert time.monotonic() - start < 15
    assert proc.returncode == TIMEOUT_RETURNCODE
    assert "started" in proc.stdout  # partial output is kept
    grandchild = int(pidfile.read_text())
    assert _gone_soon(grandchild), "grandchild survived the timeout"


def test_leftover_background_process_is_killed(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    proc = run_killing_group(
        [sys.executable, "-c", LEAVER, str(pidfile)], cwd=tmp_path, env=None, timeout=30
    )
    assert proc.returncode == 0 and proc.stdout == "bye\n"
    assert _gone_soon(int(pidfile.read_text())), "background child survived"


@pytest.mark.parametrize("kw", [{"capture_output": False}, {"text": False}, {"check": True}])
def test_rejects_unsupported_modes(tmp_path: Path, kw: dict[str, bool]) -> None:
    with pytest.raises(ValueError, match="always captures"):
        run_killing_group(["true"], cwd=tmp_path, env=None, timeout=1, **kw)


# A grandchild that leaves the group (new session) but keeps the stdout pipe open.
ESCAPER = """\
import subprocess, sys, time
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
)
open(sys.argv[1], "w").write(f"{child.pid}\\n")
print("escaping", flush=True)
time.sleep(60)
"""


def test_timeout_returns_even_if_a_process_escapes_the_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import snowbot.backends.proc as proc_mod

    monkeypatch.setattr(proc_mod, "_DRAIN_S", 0.5)
    pidfile = tmp_path / "pid"
    start = time.monotonic()
    try:
        proc = run_killing_group(
            [sys.executable, "-c", ESCAPER, str(pidfile)], cwd=tmp_path, env=None, timeout=1.5
        )
    finally:
        if pidfile.is_file():
            # Known limit: a process that calls setsid() is outside the group kill.
            os.kill(int(pidfile.read_text()), 9)
    assert time.monotonic() - start < 15
    assert proc.returncode == TIMEOUT_RETURNCODE
    assert "escaping" in proc.stdout
