"""Version pins, drift, archive, caps, and stability. Real files and real git."""

from __future__ import annotations

import json
import shutil
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from research.archive import archive_version, preserve_current_version, tag_name
from research.cli import main
from research.drift import (
    Finding,
    check_drift,
    decide_action,
    fetch_json,
    oracle_self_check,
    render_issue_body,
)
from research.errors import ArchiveRefused, ConfigError, VersionBumpRequired
from research.gitutil import commit_all, init_repo, run_git
from research.hashutil import sha256_file
from research.ledger import (
    DEFAULT_MONTHLY_CAP_USD,
    DEFAULT_PER_RUN_CAP_USD,
    evaluate_caps,
    load_ledger,
    spend_allowed,
)
from research.stability import cohen_kappa, evaluate_stability
from research.status import default_status, load_status, status_file, validate_status
from research.versioning import (
    POOLING_RULE,
    current_version_string,
    load_version,
    parse_semver,
    pins_of,
    require_version_bump,
    verify_freeze,
    version_of,
)

ROOT = Path(__file__).resolve().parents[2]
SCANNER = "2165b01dd96174ff8c963afef82b86458ceb71c9"
IMPOSSIBLE = "d4f9a149db2b9cec0fed7bab01d91c07ee10aca2"


def test_checked_in_version_matches_live_files() -> None:
    document = load_version(ROOT / "research" / "versions" / "current" / "VERSION")
    assert version_of(document) == "0.1.0"
    assert current_version_string() == "0.1.0"
    assert document["results_policy"] == POOLING_RULE
    pins = pins_of(document)
    assert pins["scanner_commit"] == SCANNER
    assert pins["impossiblebench_commit"] == IMPOSSIBLE
    assert pins["impossiblebench_status"] == "pinned"
    assert pins["inspect_version"] == "0.3.285"
    assert pins["docker_digest_status"] == "unpinned"
    sources = document["sources"]
    assert isinstance(sources, list)
    docker = next(
        item
        for item in sources
        if isinstance(item, dict) and item.get("name") == "docker_image_digests"
    )
    assert docker["status"] == "unpinned"
    assert pins["model_ids"] == ["haiku"]
    verify_freeze(ROOT)
    status = load_status(ROOT / "research" / "STATUS.json")
    assert status["schedule"] == "paused"
    assert status["version_state"] == "current"
    assert status["kill"] is False
    assert status["fix_attempts"] == 0
    assert status["version"] == "0.1.0"
    ledger = load_ledger(ROOT / "research" / "ledger.json")
    assert ledger["monthly_cap_usd"] == DEFAULT_MONTHLY_CAP_USD
    assert ledger["per_run_cap_usd"] == DEFAULT_PER_RUN_CAP_USD
    assert ledger["runs"] == []


def test_pin_change_without_version_bump_is_rejected() -> None:
    previous = load_version(ROOT / "research" / "versions" / "current" / "VERSION")
    proposed = json.loads(json.dumps(previous))
    assert isinstance(proposed, dict)
    pins = proposed["pins"]
    assert isinstance(pins, dict)
    pins["scanner_commit"] = "0" * 40
    with pytest.raises(VersionBumpRequired, match="version bump"):
        require_version_bump(previous, proposed)
    proposed["version"] = "0.2.0"
    require_version_bump(previous, proposed)
    same = json.loads(json.dumps(previous))
    assert isinstance(same, dict)
    same["version"] = "0.2.0"
    require_version_bump(previous, same)
    same["version"] = "0.0.9"
    with pytest.raises(VersionBumpRequired, match="backwards"):
        require_version_bump(previous, same)
    with pytest.raises(ConfigError, match=r"MAJOR\.MINOR\.PATCH"):
        parse_semver("1.2")


def test_live_oracle_edit_and_scanner_mismatch_are_rejected(tmp_path: Path) -> None:
    root = _bundle(tmp_path, sources=[])
    oracle = root / "research" / "configs" / "oracle_rules.yaml"
    oracle.write_text(oracle.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    with pytest.raises(VersionBumpRequired, match="version bump"):
        verify_freeze(root)
    root = _bundle(tmp_path / "scanner", sources=[])
    document = load_version(root / "research" / "versions" / "current" / "VERSION")
    pins = document["pins"]
    assert isinstance(pins, dict)
    pins["scanner_commit"] = "f" * 40
    _write_json(root / "research" / "versions" / "current" / "VERSION", document)
    with pytest.raises(VersionBumpRequired, match="scanner commit"):
        verify_freeze(root)
    paths = document["paths"]
    assert isinstance(paths, dict)
    paths.clear()
    paths["task_suite"] = "../outside.txt"
    _write_json(root / "research" / "versions" / "current" / "VERSION", document)
    with pytest.raises(ConfigError, match="escapes"):
        verify_freeze(root)


def test_drift_unpinned_outdated_and_upstream_comparison(tmp_path: Path) -> None:
    with _server(
        {
            "/inspect": b'{"info":{"version":"9.9.9"}}',
            "/match": b'{"info":{"version":"0.3.285"}}',
            "/bad": b"not-json",
            "/retired": b'{"retired":["haiku"]}',
            "/clear": b'{"retired":[]}',
            "/number": b'{"info":{"version":1}}',
        }
    ) as base:
        mismatched = _bundle(
            tmp_path / "mismatch",
            sources=[
                _source("inspect", "inspect_version", f"{base}/inspect", "info.version"),
                _source(
                    "docker_image_digests",
                    "docker_digest_status",
                    None,
                    None,
                    status="unpinned",
                ),
            ],
        )
        report = check_drift(
            mismatched,
            infrastructure_failure_flag=False,
            validate_failed=False,
            oracle_failed=False,
            timeout=2,
        )
        by_name = {item.name: item.status for item in report.findings}
        assert by_name["inspect"] == "outdated"
        assert by_name["docker_image_digests"] == "outdated"
        assert by_name["freeze"] == "current"
        assert report.outdated is True
        assert report.action == "draft_fix"
        assert report.status["schedule"] == "paused"
        assert report.status["version_state"] == "outdated"
        assert report.status["fix_attempts"] == 1
        assert "does not push" in report.issue_body
        assert report.to_json()["opened_pr"] is False
        body = render_issue_body(report)
        assert "draft_fix" in body

        matched = _bundle(
            tmp_path / "match",
            sources=[_source("inspect", "inspect_version", f"{base}/match", "info.version")],
        )
        clean = check_drift(
            matched,
            infrastructure_failure_flag=False,
            validate_failed=False,
            oracle_failed=False,
            timeout=2,
        )
        statuses = {item.name: item.status for item in clean.findings}
        assert statuses["inspect"] == "current"
        assert statuses["model_deprecation"] == "unchecked"
        assert clean.action == "none"
        assert clean.status["schedule"] == "paused"
        assert clean.status["kill"] is False

        refused = fetch_json(f"http://127.0.0.1:{_closed_port()}/nope", timeout=2)
        assert refused is None
        assert fetch_json("file:///etc/passwd", timeout=1) is None
        unread = _bundle(
            tmp_path / "unread",
            sources=[_source("inspect", "inspect_version", f"{base}/bad", "info.version")],
        )
        unread_report = check_drift(unread, timeout=2, oracle_failed=False, validate_failed=False)
        assert {item.name: item.status for item in unread_report.findings}["inspect"] == "unchecked"
        numbered = _bundle(
            tmp_path / "number",
            sources=[_source("inspect", "inspect_version", f"{base}/number", "info.version")],
        )
        numbered_report = check_drift(numbered, timeout=2)
        numbered_status = {item.name: item.status for item in numbered_report.findings}
        assert numbered_status["inspect"] == "unchecked"

        retired = _bundle(
            tmp_path / "retired",
            sources=[
                _source(
                    "model_deprecation",
                    "model_ids",
                    f"{base}/retired",
                    "retired",
                    kind="deprecation",
                )
            ],
        )
        retired_report = check_drift(retired, timeout=2)
        retired_status = {item.name: item.status for item in retired_report.findings}
        assert retired_status["model_deprecation"] == "outdated"
        caller = check_drift(matched, retired_model_ids=("haiku",), timeout=2)
        caller_status = {item.name: item.status for item in caller.findings}
        assert caller_status["model_deprecation"] == "outdated"
        clear = _bundle(
            tmp_path / "clear",
            sources=[
                _source(
                    "model_deprecation",
                    "model_ids",
                    f"{base}/clear",
                    "retired",
                    kind="deprecation",
                )
            ],
        )
        clear_report = check_drift(clear, timeout=2)
        clear_status = {item.name: item.status for item in clear_report.findings}
        assert clear_status["model_deprecation"] == "current"


def test_drift_flags_ledger_oracle_and_fix_attempts(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "flags", sources=[])
    ledger_path = tmp_path / "ledger.json"
    _write_json(
        ledger_path,
        {
            "monthly_cap_usd": 50,
            "per_run_cap_usd": 1.5,
            "runs": [
                {
                    "run_id": "r1",
                    "version": "0.1.0",
                    "spent_usd": 1.5,
                    "at": "2026-10-02",
                    "infrastructure_failure": True,
                    "scheduled": True,
                }
            ],
        },
    )
    status_path = tmp_path / "STATUS.json"
    _write_json(status_path, default_status("0.1.0"))
    before = status_path.read_bytes()
    first = check_drift(
        root,
        ledger_path=ledger_path,
        status_path=status_path,
        validate_failed=True,
        oracle_failed=True,
        today=date(2026, 10, 28),
    )
    assert status_path.read_bytes() == before
    names = {item.name: item.status for item in first.findings}
    assert names["infrastructure"] == "outdated"
    assert names["snowbot_validate"] == "outdated"
    assert names["oracle_self_check"] == "outdated"
    assert first.action == "draft_fix"
    assert first.status["fix_attempts"] == 1
    _write_json(status_path, first.status)
    second = check_drift(
        root,
        ledger_path=ledger_path,
        status_path=status_path,
        validate_failed=True,
        oracle_failed=True,
        today=date(2026, 10, 28),
    )
    assert second.status["fix_attempts"] == 2
    assert second.action == "draft_fix"
    _write_json(status_path, second.status)
    third = check_drift(
        root,
        ledger_path=ledger_path,
        status_path=status_path,
        validate_failed=True,
        oracle_failed=True,
        today=date(2026, 10, 28),
    )
    assert third.action == "stop_and_report"
    assert third.status["fix_attempts"] == 2
    assert "Stop." in third.issue_body
    assert third.to_json()["applied"] is False

    fresh = default_status("0.1.0")
    action, proposed = decide_action(
        fresh,
        (Finding("other", "outdated", "a different pin moved"),),
    )
    assert action == "draft_fix"
    assert proposed["fix_attempts"] == 1
    stopped = dict(third.status)
    action, proposed = decide_action(
        stopped,
        (Finding("other", "outdated", "a different pin moved"),),
    )
    assert action == "draft_fix"
    assert proposed["fix_attempts"] == 1

    cap_root = _bundle(tmp_path / "cap", sources=[])
    cap_ledger = tmp_path / "cap-ledger.json"
    _write_json(
        cap_ledger,
        {
            "monthly_cap_usd": 50,
            "per_run_cap_usd": 1.5,
            "runs": [
                {
                    "run_id": "big",
                    "version": "0.1.0",
                    "spent_usd": 60,
                    "at": "2026-10-03",
                    "infrastructure_failure": False,
                    "scheduled": True,
                }
            ],
        },
    )
    capped = check_drift(
        cap_root,
        ledger_path=cap_ledger,
        oracle_failed=False,
        validate_failed=False,
        today=date(2026, 10, 28),
    )
    assert capped.status["kill"] is True
    assert capped.status["schedule"] == "paused"
    assert "cap" in str(capped.status["reason"])


def test_oracle_self_check_uses_a_real_diff(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "pass", sources=[])
    rules = root / "research" / "configs" / "oracle_rules.yaml"
    passed, detail = oracle_self_check(rules, tmp_path / "work-pass")
    assert passed is True
    assert "threshold drop" in detail
    broken = rules.read_text(encoding="utf-8").replace("fail_under", "nope")
    rules.write_text(broken, encoding="utf-8")
    (rules.parent / "oracle_rules.sha256").write_text(sha256_file(rules) + "\n", encoding="utf-8")
    failed, failure = oracle_self_check(rules, tmp_path / "work-fail")
    assert failed is False
    assert "missed" in failure
    wired = check_drift(root, run_oracle_self_check=True, oracle_work=tmp_path / "wired")
    assert {item.name: item.status for item in wired.findings}["oracle_self_check"] == "outdated"


def test_caps_do_not_rewrite_the_repository_ledger(tmp_path: Path) -> None:
    path = ROOT / "research" / "ledger.json"
    before = path.read_bytes()
    status_path = ROOT / "research" / "STATUS.json"
    status_before = status_path.read_bytes()
    ledger = load_ledger(path)
    breach = evaluate_caps(
        ledger,
        version="0.1.0",
        today=date(2026, 10, 28),
        proposed_usd=100,
    )
    assert path.read_bytes() == before
    assert status_path.read_bytes() == status_before
    assert breach["schedule"] == "paused"
    assert breach["kill"] is True
    within = evaluate_caps(ledger, version="0.1.0", today=date(2026, 10, 28), proposed_usd=1.5)
    assert within["kill"] is False
    assert within["schedule"] == "paused"
    assert spend_allowed(within, human_confirmed=True) is False
    active = dict(within)
    active["schedule"] = "active"
    assert spend_allowed(active, human_confirmed=False) is False
    assert spend_allowed(active, human_confirmed=True) is True
    active["kill"] = True
    assert spend_allowed(active, human_confirmed=True) is False
    month = {
        "monthly_cap_usd": 50,
        "per_run_cap_usd": 50,
        "runs": [
            {
                "run_id": "m",
                "version": "0.1.0",
                "spent_usd": 49,
                "at": "2026-10-01",
                "infrastructure_failure": False,
                "scheduled": True,
            }
        ],
    }
    over_month = evaluate_caps(
        month,
        version="0.1.0",
        today=date(2026, 10, 28),
        proposed_usd=1.5,
    )
    assert over_month["kill"] is True
    other_month = evaluate_caps(
        month,
        version="0.1.0",
        today=date(2026, 11, 1),
        proposed_usd=1.5,
    )
    assert other_month["kill"] is False
    with pytest.raises(ConfigError):
        evaluate_caps(ledger, version="0.1.0", today=date(2026, 10, 28), proposed_usd=-1)
    bad = tmp_path / "bad-ledger.json"
    _write_json(
        bad,
        {
            "monthly_cap_usd": 50,
            "per_run_cap_usd": 1.5,
            "runs": [
                {
                    "run_id": "bad",
                    "version": "0.1.0",
                    "spent_usd": 1,
                    "at": "October",
                    "infrastructure_failure": False,
                    "scheduled": True,
                }
            ],
        },
    )
    with pytest.raises(ConfigError, match="YYYY-MM-DD"):
        load_ledger(bad)


def test_archive_moves_files_and_refuses_unmerged_or_overwrite(tmp_path: Path) -> None:
    repo = _git_version_repo(tmp_path / "merged")
    results = repo / "docs" / "research" / "results"
    results.mkdir(parents=True)
    (results / "results.jsonl").write_text('{"version":"0.1.0"}\n', encoding="utf-8")
    (results / "tables.md").write_text("# tables\n", encoding="utf-8")
    (repo / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(repo, "bump to 0.2.0")
    first = archive_version(
        repo,
        old_version="0.1.0",
        new_version="0.2.0",
        why="docker digest unpinned",
        fix_pr="https://example.test/pull/12",
        on=date(2026, 10, 28),
    )
    assert first.tag == "research-v0.1.0"
    assert first.idempotent is False
    archived = repo / "research" / "archive" / "0.1.0"
    text = (archived / "SUPERSEDED.md").read_text(encoding="utf-8")
    assert "2026-10-28" in text
    assert "docker digest unpinned" in text
    assert "https://example.test/pull/12" in text
    assert "0.2.0" in text
    assert "research-v0.1.0" in text
    assert (archived / "manifest.json").is_file()
    assert (archived / "results.jsonl").is_file()
    assert (archived / "tables.md").is_file()
    assert (archived / "catalog.yaml").read_text(encoding="utf-8") == "tasks\n"
    docs = repo / "docs" / "research" / "archive" / "0.1.0"
    assert (docs / "results.jsonl").is_file()
    assert not results.exists()
    assert run_git(repo, ["tag", "--list"]).strip() == ""
    second = archive_version(
        repo,
        old_version="0.1.0",
        new_version="0.2.0",
        why="docker digest unpinned",
        fix_pr="https://example.test/pull/12",
        on=date(2026, 10, 28),
    )
    assert second.idempotent is True
    assert (archived / "KEEP").read_text(encoding="utf-8") == "keep\n"

    unmerged = _git_version_repo(tmp_path / "unmerged")
    with pytest.raises(ArchiveRefused, match="not merged"):
        archive_version(
            unmerged,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/1",
        )
    run_git(unmerged, ["checkout", "-b", "fix"])
    (unmerged / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(unmerged, "bump on fix")
    run_git(unmerged, ["checkout", "main"])
    with pytest.raises(ArchiveRefused, match="not merged"):
        archive_version(
            unmerged,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/1",
            into="main",
        )
    moved = archive_version(
        unmerged,
        old_version="0.1.0",
        new_version="0.2.0",
        why="pin",
        fix_pr="https://example.test/pull/1",
        into="fix",
    )
    assert moved.tag == tag_name("0.1.0")

    blocked = _git_version_repo(tmp_path / "blocked")
    (blocked / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(blocked, "bump")
    dest = blocked / "research" / "archive" / "0.1.0"
    dest.mkdir(parents=True)
    (dest / "sentinel").write_text("nope\n", encoding="utf-8")
    with pytest.raises(ArchiveRefused, match="will not be overwritten"):
        archive_version(
            blocked,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/2",
        )
    assert (blocked / "research" / "versions" / "0.1.0" / "VERSION").is_file()
    assert (dest / "sentinel").read_text(encoding="utf-8") == "nope\n"
    with pytest.raises(ArchiveRefused, match="greater"):
        archive_version(
            blocked,
            old_version="0.2.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/2",
        )
    with pytest.raises(ArchiveRefused, match="why"):
        archive_version(
            blocked,
            old_version="0.1.0",
            new_version="0.3.0",
            why="  ",
            fix_pr="https://example.test/pull/2",
        )


def test_stability_requires_every_recorded_input(tmp_path: Path) -> None:
    payload = _stable_payload()
    report = evaluate_stability(payload)
    assert report.stable is True
    assert report.draft_pr_body is not None
    assert "`schedule`: `paused`" in report.draft_pr_body
    assert "`version_state`: `stable`" in report.draft_pr_body
    assert report.to_json()["opened_pr"] is False
    assert report.to_json()["status_edited"] is False
    status_path = ROOT / "research" / "STATUS.json"
    before = status_path.read_bytes()
    assert evaluate_stability(payload).stable is True
    assert status_path.read_bytes() == before

    unevaluated = dict(payload)
    unevaluated["kappa_target"] = None
    unevaluated["error_target"] = None
    held = evaluate_stability(unevaluated)
    assert held.stable is False
    assert held.checks["oracle_accuracy"] == "not_evaluated"
    assert held.draft_pr_body is None

    short = dict(payload)
    runs = list(payload["runs"])
    assert isinstance(runs, list)
    short["runs"] = runs[:2]
    assert evaluate_stability(short).checks["consecutive_runs"].startswith("fail")
    changed = json.loads(json.dumps(payload))
    assert isinstance(changed["runs"], list)
    changed["runs"][1]["scanner_commit"] = "f" * 40
    assert "changed" in evaluate_stability(changed).checks["pins_unchanged"]
    noisy = dict(payload)
    noisy["aa_difference"] = 0.2
    assert evaluate_stability(noisy).checks["aa_noise"].startswith("fail")
    drifted = dict(payload)
    drifted["drift_outdated"] = True
    assert "outdated" in evaluate_stability(drifted).checks["drift_and_ci"]
    red = dict(payload)
    red["ci_green"] = False
    assert "architect-gate" in evaluate_stability(red).checks["drift_and_ci"]
    omitted = dict(payload)
    del omitted["drift_unchecked"]
    assert "unchecked" in evaluate_stability(omitted).checks["drift_and_ci"]
    weak = dict(payload)
    weak["labels"] = [
        {"oracle": "yes", "human": "yes"},
        {"oracle": "yes", "human": "no"},
        {"oracle": "no", "human": "no"},
        {"oracle": "no", "human": "no"},
    ]
    weak["kappa_target"] = 0.9
    weak["error_target"] = 0.0
    assert evaluate_stability(weak).checks["oracle_accuracy"].startswith("fail")
    kappa, error = cohen_kappa([("yes", "yes"), ("yes", "yes"), ("no", "no"), ("no", "no")])
    assert kappa == pytest.approx(1.0)
    assert error == 0.0
    with pytest.raises(ConfigError):
        evaluate_stability({"runs": [], "aa_difference": "high", "aa_tolerance": 0.1})


def test_cli_version_drift_stability_caps_and_archive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["version", "--check", "--root", str(ROOT)]) == 0
    assert capsys.readouterr().out.strip() == "0.1.0"

    root = _bundle(tmp_path / "cli", sources=[])
    status = tmp_path / "STATUS.json"
    _write_json(status, default_status("0.1.0"))
    before = status.read_bytes()
    assert (
        main(
            [
                "drift-check",
                "--root",
                str(root),
                "--status",
                str(status),
                "--no-oracle-self-check",
                "--infrastructure-ok",
                "--validate-passed",
            ]
        )
        == 0
    )
    assert status.read_bytes() == before
    printed = json.loads(capsys.readouterr().out)
    assert printed["applied"] is False
    assert printed["dry_run"] is True
    assert (
        main(
            [
                "drift-check",
                "--root",
                str(root),
                "--no-dry-run",
                "--no-oracle-self-check",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "does not push" in captured.err
    assert json.loads(captured.out)["opened_pr"] is False

    stable_path = tmp_path / "stable.json"
    _write_json(stable_path, _stable_payload())
    assert main(["stability", "--input", str(stable_path)]) == 0
    stable = json.loads(capsys.readouterr().out)
    assert stable["stable"] is True
    assert "paused" in stable["draft_pr_body"]
    assert "stable" in stable["draft_pr_body"]

    ledger_before = (ROOT / "research" / "ledger.json").read_bytes()
    assert (
        main(
            [
                "caps",
                "--ledger",
                str(ROOT / "research" / "ledger.json"),
                "--proposed-usd",
                "100",
                "--today",
                "2026-10-28",
                "--human-confirmed",
            ]
        )
        == 0
    )
    assert (ROOT / "research" / "ledger.json").read_bytes() == ledger_before
    caps = json.loads(capsys.readouterr().out)
    assert caps["applied"] is False
    assert caps["status"]["kill"] is True
    assert caps["status"]["schedule"] == "paused"
    assert caps["spend_allowed"] is False

    repo = _git_version_repo(tmp_path / "cli-archive")
    (repo / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(repo, "bump")
    assert (
        main(
            [
                "archive",
                "--root",
                str(repo),
                "--old-version",
                "0.1.0",
                "--new-version",
                "0.2.0",
                "--why",
                "unpinned digest",
                "--fix-pr",
                "https://example.test/pull/4",
                "--on",
                "2026-10-28",
            ]
        )
        == 0
    )
    archived_out = capsys.readouterr().out
    assert "research-v0.1.0" in archived_out
    assert "not pushed" in archived_out
    assert run_git(repo, ["tag", "--list"]).strip() == ""


def test_archive_and_document_edges(tmp_path: Path) -> None:
    missing = tmp_path / "missing-current"
    missing.mkdir()
    with pytest.raises(ArchiveRefused, match="missing"):
        preserve_current_version(missing)
    with pytest.raises(ArchiveRefused, match="not merged"):
        archive_version(
            missing,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/9",
        )
    repo = _git_version_repo(tmp_path / "edges")
    (repo / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(repo, "bump")
    with pytest.raises(ArchiveRefused, match="fix PR"):
        archive_version(
            repo,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr=" ",
        )
    docs_dest = repo / "docs" / "research" / "archive" / "0.1.0"
    docs_dest.mkdir(parents=True)
    results = repo / "docs" / "research" / "results"
    results.mkdir()
    (results / "results.jsonl").write_text("row\n", encoding="utf-8")
    with pytest.raises(ArchiveRefused, match="will not be overwritten"):
        archive_version(
            repo,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/9",
        )
    assert (repo / "research" / "versions" / "0.1.0" / "VERSION").is_file()
    docs_dest.rmdir()
    (results / "results.jsonl").unlink()
    results.rmdir()
    archive_version(
        repo,
        old_version="0.1.0",
        new_version="0.2.0",
        why="pin",
        fix_pr="https://example.test/pull/9",
    )
    late = repo / "docs" / "research" / "results"
    late.mkdir(parents=True)
    (late / "tables.md").write_text("late\n", encoding="utf-8")
    again = archive_version(
        repo,
        old_version="0.1.0",
        new_version="0.2.0",
        why="pin",
        fix_pr="https://example.test/pull/9",
    )
    assert again.idempotent is True
    assert (repo / "docs" / "research" / "archive" / "0.1.0" / "tables.md").is_file()
    gone = _git_version_repo(tmp_path / "gone")
    (gone / "research" / "versions" / "current" / "VERSION").write_text(
        json.dumps({"version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    commit_all(gone, "bump")
    shutil.rmtree(gone / "research" / "versions" / "0.1.0")
    with pytest.raises(ArchiveRefused, match="nothing to archive"):
        archive_version(
            gone,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/9",
        )
    broken = _git_version_repo(tmp_path / "broken-json")
    version_path = broken / "research" / "versions" / "current" / "VERSION"
    version_path.write_text("not-json\n", encoding="utf-8")
    commit_all(broken, "bad version file")
    with pytest.raises(ArchiveRefused, match="not merged"):
        archive_version(
            broken,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/9",
        )
    version_path.write_text("[1]\n", encoding="utf-8")
    commit_all(broken, "version file is a list")
    with pytest.raises(ArchiveRefused, match="not merged"):
        archive_version(
            broken,
            old_version="0.1.0",
            new_version="0.2.0",
            why="pin",
            fix_pr="https://example.test/pull/9",
        )

    raw = tmp_path / "bad.json"
    raw.write_text("[", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_version(raw)
    raw.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_version(raw)
    status = default_status("0.1.0")
    status["version_state"] = "draft"
    with pytest.raises(ConfigError, match="version_state"):
        validate_status(status)
    status["version_state"] = "current"
    status["kill"] = "no"
    with pytest.raises(ConfigError, match="kill"):
        validate_status(status)
    status["kill"] = False
    status["fix_attempts"] = -1
    with pytest.raises(ConfigError, match="fix_attempts"):
        validate_status(status)
    status["fix_attempts"] = 0
    status["last_drift_signature"] = 3
    with pytest.raises(ConfigError, match="last_drift_signature"):
        validate_status(status)
    assert status_file(tmp_path).name == "STATUS.json"


def test_status_schema_rejects_bad_values() -> None:
    document = default_status("0.1.0")
    validate_status(document)
    document["schedule"] = "active"
    validate_status(document)
    document["schedule"] = "inactive"
    with pytest.raises(ConfigError, match="schedule"):
        validate_status(document)
    document["schedule"] = "paused"
    document["fix_attempts"] = True
    with pytest.raises(ConfigError, match="fix_attempts"):
        validate_status(document)


def _bundle(tmp_path: Path, *, sources: list[dict[str, object]]) -> Path:
    root = tmp_path / "repo"
    oracle = (
        "schema_version: 1\n"
        f'scanner_commit: "{SCANNER}"\n'
        "gate_paths: [pyproject.toml]\n"
        "test_path_regex: 'test_'\n"
        "circumvention_regexes: ['monkeypatch']\n"
        "taxa:\n"
        "  - id: threshold_drop\n"
        "    mode: threshold_decreased\n"
        "    count_regexes: ['fail_under\\s*[=:]\\s*[0-9]+']\n"
        "    file_suffixes: ['.toml']\n"
    )
    files = {
        "research/tasks/catalog.yaml": "catalog\n",
        "research/conditions.yaml": "conditions\n",
        "research/configs/oracle_rules.yaml": oracle,
    }
    for rel, text in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    digest = sha256_file(root / "research" / "configs" / "oracle_rules.yaml")
    pin = root / "research" / "configs" / "oracle_rules.sha256"
    pin.write_text(digest + "\n", encoding="utf-8")
    snap = root / "research" / "versions" / "current" / "snapshots"
    snap.mkdir(parents=True)
    mapping = {
        "catalog.yaml": "research/tasks/catalog.yaml",
        "conditions.yaml": "research/conditions.yaml",
        "oracle_rules.yaml": "research/configs/oracle_rules.yaml",
    }
    for name, rel in mapping.items():
        (snap / name).write_bytes((root / rel).read_bytes())
    catalog_hash = sha256_file(root / "research" / "tasks" / "catalog.yaml")
    oracle_hash = sha256_file(root / "research" / "configs" / "oracle_rules.yaml")
    conditions_hash = sha256_file(root / "research" / "conditions.yaml")
    document: dict[str, object] = {
        "schema_version": 1,
        "version": "0.1.0",
        "results_policy": POOLING_RULE,
        "pins": {
            "task_suite_sha256": catalog_hash,
            "oracle_config_sha256": oracle_hash,
            "conditions_sha256": conditions_hash,
            "scanner_commit": SCANNER,
            "inspect_version": "0.3.285",
            "agent_clis": {"claude": "v2.1.312", "codex": "rust-v0.165.0"},
            "model_ids": ["haiku"],
            "docker_image_digests": [],
            "docker_digest_status": "unpinned",
            "impossiblebench_commit": IMPOSSIBLE,
            "impossiblebench_status": "pinned",
        },
        "paths": {
            "task_suite": "research/tasks/catalog.yaml",
            "oracle_config": "research/configs/oracle_rules.yaml",
            "conditions": "research/conditions.yaml",
            "task_suite_snapshot": "research/versions/current/snapshots/catalog.yaml",
            "oracle_config_snapshot": "research/versions/current/snapshots/oracle_rules.yaml",
            "conditions_snapshot": "research/versions/current/snapshots/conditions.yaml",
        },
        "sources": sources,
    }
    _write_json(root / "research" / "versions" / "current" / "VERSION", document)
    return root


def _source(
    name: str,
    pin_path: str,
    url: str | None,
    json_path: str | None,
    *,
    status: str = "pinned",
    kind: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "status": status,
        "pin_path": pin_path,
        "url": url,
        "json_path": json_path,
    }
    if kind is not None:
        body["kind"] = kind
    return body


def _git_version_repo(path: Path) -> Path:
    init_repo(path)
    current = path / "research" / "versions" / "current"
    current.mkdir(parents=True)
    (current / "VERSION").write_text(json.dumps({"version": "0.1.0"}) + "\n", encoding="utf-8")
    (current / "catalog.yaml").write_text("tasks\n", encoding="utf-8")
    (current / "manifest.json").write_text("{}\n", encoding="utf-8")
    (current / "results.jsonl").write_text("{}\n", encoding="utf-8")
    (current / "tables.md").write_text("# t\n", encoding="utf-8")
    preserve_current_version(path)
    keep = path / "research" / "versions" / "0.1.0" / "KEEP"
    keep.write_text("keep\n", encoding="utf-8")
    again = preserve_current_version(path)
    assert again == path / "research" / "versions" / "0.1.0"
    assert keep.read_text(encoding="utf-8") == "keep\n"
    commit_all(path, "research version 0.1.0")
    return path


def _stable_payload() -> dict[str, object]:
    run = {
        "version": "0.1.0",
        "scheduled": True,
        "infrastructure_failure": False,
        "oracle_config_sha256": "a" * 64,
        "task_suite_sha256": "b" * 64,
        "scanner_commit": SCANNER,
        "conditions_sha256": "c" * 64,
        "pins_sha256": "d" * 64,
    }
    return {
        "runs": [dict(run), dict(run), dict(run)],
        "aa_difference": 0.01,
        "aa_tolerance": 0.05,
        "drift_outdated": False,
        "drift_unchecked": False,
        "ci_green": True,
        "kappa_target": 0.5,
        "error_target": 0.1,
        "labels": [
            {"oracle": "yes", "human": "yes"},
            {"oracle": "yes", "human": "yes"},
            {"oracle": "no", "human": "no"},
            {"oracle": "no", "human": "no"},
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@contextmanager
def _server(routes: dict[str, bytes]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
