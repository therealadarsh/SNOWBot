"""Regression tests for lesson index, evidence admission, and playbook precedence.

Inputs are the repository's real lesson YAML and AGENTS.md text, exercised through
the snowbot CLI (or the store/playbook functions the CLI calls).
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import yaml
from typer.testing import CliRunner

from snowbot.cli import app
from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event

runner = CliRunner()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_PROPOSED = _REPO_ROOT / ".snowbot" / "memory" / "lessons" / "proposed"


def _real_proposed_sources() -> list[Path]:
    sources = sorted(_REAL_PROPOSED.glob("*.yaml"))
    assert sources, "expected committed lessons under .snowbot/memory/lessons/proposed"
    return sources


def _copy_real_lessons(dest_dir: Path) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    for src in _real_proposed_sources():
        (dest_dir / src.name).write_bytes(src.read_bytes())
        payload = yaml.safe_load(src.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        ids.append(str(payload["id"]))
    return ids


def _config(tmp_path: Path, *, root: Path) -> Path:
    memory = tmp_path / "memory"
    config = tmp_path / "snowbot.yaml"
    config.write_text(
        "schema_version: 1\n"
        "project:\n"
        f"  root: {root}\n"
        f"  memory_dir: {memory}\n"
        "  agents_file: AGENTS.md\n",
        encoding="utf-8",
    )
    return config


def test_cli_accepts_real_lesson_addressed_by_id(tmp_path: Path) -> None:
    """`lesson accept` finds committed lessons by id, even when the filename differs."""
    config = _config(tmp_path, root=_REPO_ROOT)
    ids = _copy_real_lessons(tmp_path / "memory" / "lessons" / "proposed")
    assert "lsn-changelog" in ids
    result = runner.invoke(app, ["lesson", "accept", "lsn-changelog", "--config", str(config)])
    assert result.exit_code == 0, result.output
    accepted = tmp_path / "memory" / "lessons" / "accepted"
    assert any(path.is_file() for path in accepted.glob("*.yaml"))


def test_accept_refuses_real_lesson_when_evidence_file_is_missing(tmp_path: Path) -> None:
    """A committed lesson cannot be accepted when its file evidence is not in the project."""
    config = _config(tmp_path, root=tmp_path)
    ids = _copy_real_lessons(tmp_path / "memory" / "lessons" / "proposed")
    assert "lsn-changelog" in ids
    result = runner.invoke(app, ["lesson", "accept", "lsn-changelog", "--config", str(config)])
    assert result.exit_code != 0
    assert "evidence" in result.output.lower()
    assert "CHANGELOG.md" in result.output


def test_accept_real_lesson_whose_evidence_is_an_existing_pull_request(tmp_path: Path) -> None:
    """lsn-pr-size cites pull/1, which exists on GitHub and in a full local history."""
    config = _config(tmp_path, root=_REPO_ROOT)
    ids = _copy_real_lessons(tmp_path / "memory" / "lessons" / "proposed")
    assert "lsn-pr-size" in ids
    result = runner.invoke(app, ["lesson", "accept", "lsn-pr-size", "--config", str(config)])
    assert result.exit_code == 0, result.output


def test_accept_real_pull_request_when_history_does_not_mention_it(tmp_path: Path) -> None:
    """Shallow clones still accept the real pull/1 URL from the committed lesson."""
    clone = tmp_path / "clone"
    clone.mkdir()
    subprocess.run(["git", "init"], cwd=clone, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=clone, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "shallow checkout"],
        cwd=clone,
        check=True,
        capture_output=True,
    )
    history = subprocess.run(
        ["git", "log", "--format=%s%n%b"],
        cwd=clone,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "#1" not in history.stdout
    (clone / "CONTRIBUTING.md").write_bytes((_REPO_ROOT / "CONTRIBUTING.md").read_bytes())
    source = (_REAL_PROPOSED / "pr-size-discipline.yaml").read_bytes()
    assert b"https://github.com/therealadarsh/SNOWBot/pull/1" in source
    proposed = clone / ".snowbot" / "memory" / "lessons" / "proposed"
    proposed.mkdir(parents=True)
    (proposed / "pr-size-discipline.yaml").write_bytes(source)
    config = clone / "snowbot.yaml"
    memory = clone / ".snowbot" / "memory"
    config.write_text(
        f"schema_version: 1\nproject:\n  root: {clone}\n  memory_dir: {memory}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["lesson", "accept", "lsn-pr-size", "--config", str(config)])
    assert result.exit_code == 0, result.output


def test_accept_lesson_citing_a_recorded_stop_event(tmp_path: Path) -> None:
    """Evidence may be the id of a stop event written by the stop recorder."""
    config = _config(tmp_path, root=tmp_path)
    layout = MemoryLayout.from_project_root(tmp_path, tmp_path / "memory")
    recorded = capture_stop_event(
        layout,
        StopKind.VALIDATOR_FAIL,
        phase="1b",
        detail="phase 1b validation failed",
    )
    assert recorded is not None
    payload = json.loads(recorded.read_text(encoding="utf-8"))
    stop_id = str(payload["id"])
    added = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "Carry the validator stop forward",
            "--body",
            "Evidence is the stop event recorded for this phase.",
            "--evidence-ref",
            stop_id,
            "--config",
            str(config),
        ],
    )
    assert added.exit_code == 0, added.output
    lesson_id = added.stdout.split()[1].strip(".")
    accepted = runner.invoke(app, ["lesson", "accept", lesson_id, "--config", str(config)])
    assert accepted.exit_code == 0, accepted.output


def _prohibited_clause_from_agents(agents_text: str) -> str:
    """Return the action forbidden by the committed 'never … secrets' rule."""
    for line in agents_text.splitlines():
        lowered = line.lower()
        marker = "never "
        index = lowered.find(marker)
        if index >= 0 and "secret" in lowered:
            return line[index + len(marker) :].strip().strip(".").strip("`").strip()
    msg = "AGENTS.md has no 'never … secret' safety rule"
    raise AssertionError(msg)


def test_accept_refuses_pull_request_missing_from_git_history(tmp_path: Path) -> None:
    """The real PR lesson is refused when its pull number is not in git history."""
    source = (_REAL_PROPOSED / "pr-size-discipline.yaml").read_text(encoding="utf-8")
    real_ref = "https://github.com/therealadarsh/SNOWBot/pull/1"
    assert real_ref in source
    absent = "999999991"
    history = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "log", "--all", "--format=%s%n%b"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"#{absent}" not in history.stdout
    config = _config(tmp_path, root=_REPO_ROOT)
    dest = tmp_path / "memory" / "lessons" / "proposed"
    dest.mkdir(parents=True)
    (dest / "pr-size-discipline.yaml").write_text(
        source.replace("/pull/1", f"/pull/{absent}"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["lesson", "accept", "lsn-pr-size", "--config", str(config)])
    assert result.exit_code != 0
    assert absent in result.output


def test_accept_refuses_stop_id_that_was_not_recorded(tmp_path: Path) -> None:
    """A UUID that is not the id of a recorded stop event does not admit a lesson."""
    config = _config(tmp_path, root=tmp_path)
    layout = MemoryLayout.from_project_root(tmp_path, tmp_path / "memory")
    recorded = capture_stop_event(layout, StopKind.GATE_REJECTED, detail="unrelated stop")
    assert recorded is not None
    real_id = str(json.loads(recorded.read_text(encoding="utf-8"))["id"])
    missing = str(uuid.uuid4())
    assert missing != real_id
    added = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "Cite a stop that was not recorded",
            "--body",
            "This evidence id is not in the stops directory.",
            "--evidence-ref",
            missing,
            "--config",
            str(config),
        ],
    )
    assert added.exit_code == 0, added.output
    lesson_id = added.stdout.split()[1].strip(".")
    refused = runner.invoke(app, ["lesson", "accept", lesson_id, "--config", str(config)])
    assert refused.exit_code != 0
    assert missing in refused.output


def test_playbook_filters_lessons_through_agents_precedence(tmp_path: Path) -> None:
    """Accepted lessons that recommend a forbidden AGENTS.md action stay out of PLAYBOOK.md."""
    agents_text = (_REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    prohibited = _prohibited_clause_from_agents(agents_text)
    config = _config(tmp_path, root=_REPO_ROOT)
    _copy_real_lessons(tmp_path / "memory" / "lessons" / "proposed")

    kept = runner.invoke(app, ["lesson", "accept", "lsn-changelog", "--config", str(config)])
    assert kept.exit_code == 0, kept.output

    contradicting = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "Contradicts AGENTS.md",
            "--body",
            prohibited,
            "--evidence-ref",
            "AGENTS.md",
            "--config",
            str(config),
        ],
    )
    assert contradicting.exit_code == 0, contradicting.output
    contradicting_id = contradicting.stdout.split()[1].strip(".")
    assert (
        runner.invoke(
            app, ["lesson", "accept", contradicting_id, "--config", str(config)]
        ).exit_code
        == 0
    )

    restating = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "Restates AGENTS.md safety",
            "--body",
            "never " + prohibited,
            "--evidence-ref",
            "AGENTS.md",
            "--config",
            str(config),
        ],
    )
    assert restating.exit_code == 0, restating.output
    restating_id = restating.stdout.split()[1].strip(".")
    assert (
        runner.invoke(app, ["lesson", "accept", restating_id, "--config", str(config)]).exit_code
        == 0
    )

    generated = runner.invoke(app, ["playbook", "--config", str(config)])
    assert generated.exit_code == 0, generated.output
    playbook = (tmp_path / "memory" / "PLAYBOOK.md").read_text(encoding="utf-8")
    assert "Record user-visible changes under CHANGELOG Unreleased" in playbook
    assert "Restates AGENTS.md safety" in playbook
    assert "Contradicts AGENTS.md" not in playbook


def test_real_lessons_listed_and_indexed_once(tmp_path: Path, monkeypatch) -> None:
    """INDEX.yaml and `lesson list` must include each committed lesson a single time."""
    expected_ids = _copy_real_lessons(tmp_path / ".snowbot" / "memory" / "lessons" / "proposed")
    monkeypatch.chdir(tmp_path)

    listed = runner.invoke(app, ["lesson", "list"])
    assert listed.exit_code == 0, listed.stdout
    listed_ids = [line.split("\t", 1)[0] for line in listed.stdout.splitlines() if line.strip()]
    assert sorted(listed_ids) == sorted(expected_ids)

    evidence = tmp_path / "CHANGELOG.md"
    evidence.write_text("changelog\n", encoding="utf-8")
    added = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "Trigger index rebuild",
            "--body",
            "Rebuilds INDEX.yaml from the real lesson files.",
            "--evidence-ref",
            "CHANGELOG.md",
        ],
    )
    assert added.exit_code == 0, added.stdout
    index_payload = yaml.safe_load(
        (tmp_path / ".snowbot" / "memory" / "lessons" / "INDEX.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(index_payload, dict)
    index_ids = [str(entry["id"]) for entry in index_payload["lessons"]]
    assert len(index_ids) == len(set(index_ids))
    for lesson_id in expected_ids:
        assert index_ids.count(lesson_id) == 1
