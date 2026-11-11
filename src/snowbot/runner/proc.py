"""Run a child process in its own process group and kill the whole group on timeout.

``subprocess.run(timeout=...)`` kills only the direct child. A test suite that forks workers,
or an agent-written test that spawns a sleeper, would keep running after the gate gave up.
Here the child starts a new session, so every process it spawns shares its process group, and
a timeout sends ``SIGKILL`` to that group.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

TIMEOUT_RETURNCODE = -9
# After the group is killed, how long to wait for pipes held by escaped processes to close.
_DRAIN_S = 5.0


def _kill_group(pgid: int) -> None:
    # ProcessLookupError: the group is already gone. PermissionError: macOS reports it for a
    # group whose only member is a zombie. Neither leaves anything to kill.
    with contextlib.suppress(OSError):
        os.killpg(pgid, signal.SIGKILL)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def run_killing_group(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    env: Mapping[str, str] | None,
    timeout: float,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` with captured text output; on timeout kill its process group.

    The keyword arguments mirror ``subprocess.run`` so callers can inject either. Output is
    always captured as text; ``capture_output``, ``text`` and ``check`` exist for signature
    compatibility only and must keep their defaults. A timeout returns returncode ``-9`` and
    whatever output arrived before the kill. Leftover members of the group (background
    processes the child started) are killed after a normal exit too.
    """
    if not capture_output or not text or check:
        msg = "run_killing_group always captures text output and never raises on exit code"
        raise ValueError(msg)
    args = list(argv)
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as first:
        _kill_group(proc.pid)
        try:
            out, err = proc.communicate(timeout=_DRAIN_S)
        except subprocess.TimeoutExpired as second:
            # A process that left the group still holds a pipe open. Keep what arrived.
            out = _text(second.stdout) or _text(first.stdout)
            err = _text(second.stderr) or _text(first.stderr)
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            proc.wait()
        return subprocess.CompletedProcess(args, TIMEOUT_RETURNCODE, out or "", err or "")
    finally:
        _kill_group(proc.pid)
    return subprocess.CompletedProcess(args, proc.returncode, out or "", err or "")


__all__ = ["TIMEOUT_RETURNCODE", "run_killing_group"]
