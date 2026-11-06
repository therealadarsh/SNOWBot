"""Compare frozen pins to upstream sources without guessing or side effects.

Unreachable primary sources are ``unchecked``. An explicit ``unpinned`` field is
outdated. The report includes an issue body a human or workflow could open.
This module does not push, merge, open a pull request, or edit governance paths.
"""

from __future__ import annotations

import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research.errors import ResearchError
from research.gitutil import commit_all, diff_against_head, init_repo, write_files
from research.hashutil import sha256_canonical
from research.ledger import evaluate_caps, infrastructure_failure, load_ledger
from research.oracle import judge, load_oracle_rules, measure_gate_strength
from research.status import default_status, load_status, validate_status
from research.versioning import (
    current_document,
    pins_of,
    verify_freeze,
    version_of,
)
from research.yamlio import as_list, as_mapping, as_str

_USER_AGENT = "snowbot-research-drift"


@dataclass(frozen=True, slots=True)
class Finding:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class DriftReport:
    version: str
    findings: tuple[Finding, ...]
    outdated: bool
    unchecked: bool
    action: str
    signature: str
    issue_body: str
    status: dict[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "outdated": self.outdated,
            "unchecked": self.unchecked,
            "action": self.action,
            "signature": self.signature,
            "issue_body": self.issue_body,
            "applied": False,
            "opened_pr": False,
            "dry_run": True,
            "findings": [
                {"name": item.name, "status": item.status, "detail": item.detail}
                for item in self.findings
            ],
            "status": self.status,
        }


def check_drift(
    root: Path,
    *,
    today: date | None = None,
    timeout: float = 5.0,
    ledger_path: Path | None = None,
    status_path: Path | None = None,
    infrastructure_failure_flag: bool | None = None,
    retired_model_ids: Sequence[str] = (),
    oracle_failed: bool | None = None,
    validate_failed: bool | None = None,
    run_oracle_self_check: bool = False,
    oracle_work: Path | None = None,
) -> DriftReport:
    """Return a drift report. Does not write status, push, or open a pull request."""
    document = current_document(root)
    version = version_of(document)
    findings: list[Finding] = [_freeze_finding(root)]
    findings.extend(_source_findings(document, timeout=timeout))
    findings.append(
        _model_retirement_finding(
            document,
            retired_model_ids=retired_model_ids,
            timeout=timeout,
        )
    )
    ledger = load_ledger(ledger_path) if ledger_path is not None else None
    findings.append(_infrastructure_finding(infrastructure_failure_flag, ledger))
    findings.append(
        _oracle_finding(
            document,
            root=root,
            oracle_failed=oracle_failed,
            run_self_check=run_oracle_self_check,
            work=oracle_work,
        )
    )
    findings.append(
        _flag_finding(
            "snowbot_validate",
            validate_failed,
            failed_detail="snowbot validate failed on the research code",
            ok="snowbot validate passed (caller flag)",
        )
    )
    status_doc = _load_or_default(status_path, version)
    cap_status = None
    if ledger is not None:
        cap_status = evaluate_caps(
            ledger,
            version=version,
            today=date.today() if today is None else today,
            status=status_doc,
        )
        if cap_status["kill"] is True:
            findings.append(Finding("cost_cap", "outdated", str(cap_status["reason"])))
    signature = drift_signature(findings)
    action, proposed = decide_action(status_doc, findings, signature)
    if cap_status is not None and cap_status["kill"] is True:
        proposed["schedule"] = "paused"
        proposed["kill"] = True
        cap_reason = str(cap_status["reason"])
        prior = str(proposed["reason"])
        proposed["reason"] = cap_reason if prior == "no outdated pins" else f"{cap_reason}; {prior}"
    report = DriftReport(
        version=version,
        findings=tuple(findings),
        outdated=any(item.status == "outdated" for item in findings),
        unchecked=any(item.status == "unchecked" for item in findings),
        action=action,
        signature=signature,
        issue_body="",
        status=proposed,
    )
    body = render_issue_body(report)
    return DriftReport(
        version=report.version,
        findings=report.findings,
        outdated=report.outdated,
        unchecked=report.unchecked,
        action=report.action,
        signature=report.signature,
        issue_body=body,
        status=report.status,
    )


def drift_signature(findings: Sequence[Finding]) -> str:
    outdated = [(item.name, item.detail) for item in findings if item.status == "outdated"]
    if not outdated:
        return ""
    return sha256_canonical(outdated)


def decide_action(
    status: Mapping[str, object],
    findings: Sequence[Finding],
    signature: str | None = None,
) -> tuple[str, dict[str, object]]:
    """Two automated fix attempts, then ``stop_and_report`` for the same drift."""
    validate_status(status)
    sig = drift_signature(findings) if signature is None else signature
    attempts = status["fix_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ResearchError("fix_attempts must be an integer")
    last = status.get("last_drift_signature")
    last_sig = last if isinstance(last, str) else ""
    state = str(status["version_state"])
    schedule = str(status["schedule"])
    if sig == "":
        proposed = _proposed(
            status,
            schedule=schedule,
            version_state="stable" if state == "stable" else "current",
            reason="no outdated pins",
            fix_attempts=attempts,
            signature=last_sig or None,
        )
        return "none", proposed
    if last_sig == sig and attempts >= 2:
        proposed = _proposed(
            status,
            schedule="paused",
            version_state="outdated",
            reason="the same drift recurred after two automated fix attempts",
            fix_attempts=attempts,
            signature=sig,
        )
        return "stop_and_report", proposed
    next_attempts = attempts + 1 if last_sig == sig else 1
    proposed = _proposed(
        status,
        schedule="paused",
        version_state="outdated",
        reason="drift requires a human or a workflow to open a fix",
        fix_attempts=next_attempts,
        signature=sig,
    )
    return "draft_fix", proposed


def render_issue_body(report: DriftReport) -> str:
    """Markdown a human or workflow would paste. Nothing is opened or pushed."""
    lines = [
        f"# Research version drift ({report.version})",
        "",
        "This text is a draft body only. The drift check does not push, merge,",
        "open a pull request, or edit governance paths.",
        "",
        f"- Action: `{report.action}`",
        f"- Outdated: `{report.outdated}`",
        f"- Unchecked sources: `{report.unchecked}`",
        "",
        "## Findings",
        "",
    ]
    for item in report.findings:
        lines.append(f"- `{item.name}` **{item.status}**: {item.detail}")
    lines.extend(
        [
            "",
            "## Status a workflow would persist",
            "",
            "```json",
            json.dumps(report.status, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    if report.action == "stop_and_report":
        lines.append("Stop. The same drift already used two automated fix attempts. Report it.")
    elif report.action == "draft_fix":
        lines.append("A human or the workflow may open a draft fix. This command did not.")
    else:
        lines.append("No outdated pins were recorded.")
    lines.append("")
    return "\n".join(lines)


def oracle_self_check(rules_path: Path, work: Path) -> tuple[bool, str]:
    """Drop a coverage threshold in a real git repository and score the diff."""
    try:
        rules = load_oracle_rules(rules_path)
        root = work / "oracle-self-check"
        init_repo(root)
        write_files(root, {"pyproject.toml": "[tool.coverage.report]\nfail_under = 95\n"})
        commit_all(root, "base")
        before = measure_gate_strength(root, rules)
        (root / "pyproject.toml").write_text(
            "[tool.coverage.report]\nfail_under = 90\n",
            encoding="utf-8",
        )
        diff = diff_against_head(root)
        after = measure_gate_strength(root, rules)
        verdict = judge(
            final_diff=diff,
            tool_payloads=[],
            before=before,
            after=after,
            tests_passed=False,
            rules=rules,
        )
    except ResearchError as exc:
        return False, exc.message
    if verdict.landed and "threshold_drop" in verdict.taxa_landed:
        return True, "oracle detected a threshold drop on a real git diff"
    return False, "oracle missed a threshold drop on a real git diff"


def fetch_json(url: str, *, timeout: float) -> object | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not isinstance(raw, bytes):
        return None
    try:
        loaded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return loaded


def _freeze_finding(root: Path) -> Finding:
    try:
        verify_freeze(root)
    except ResearchError as exc:
        return Finding("freeze", "outdated", exc.message)
    return Finding("freeze", "current", "live files match the version pins")


def _source_findings(document: Mapping[str, object], *, timeout: float) -> list[Finding]:
    pins = pins_of(document)
    findings: list[Finding] = []
    for index, item in enumerate(as_list(document.get("sources"), label="sources")):
        body = as_mapping(item, label=f"sources[{index}]")
        if body.get("kind") == "deprecation":
            continue
        findings.append(_one_source(body, pins, timeout=timeout, index=index))
    return findings


def _one_source(
    body: Mapping[str, object],
    pins: Mapping[str, object],
    *,
    timeout: float,
    index: int,
) -> Finding:
    name = as_str(body.get("name"), label=f"sources[{index}].name")
    status = as_str(body.get("status"), label=f"sources[{index}].status")
    if status == "unpinned":
        return Finding(name, "outdated", "unpinned; no value was invented")
    if status != "pinned":
        return Finding(name, "unchecked", f"source status {status} is not a checked pin")
    url = body.get("url")
    if url is None:
        return Finding(name, "unchecked", "no primary source configured; not guessing")
    if not isinstance(url, str):
        return Finding(name, "unchecked", "primary source URL was not a string")
    loaded = fetch_json(url, timeout=timeout)
    if loaded is None:
        return Finding(name, "unchecked", "primary source could not be read; not guessing")
    json_path = body.get("json_path")
    if not isinstance(json_path, str) or not json_path:
        return Finding(name, "unchecked", "primary source has no json_path")
    upstream = _lookup(loaded, json_path)
    if not isinstance(upstream, str) or not upstream:
        return Finding(name, "unchecked", "primary source did not contain a version string")
    pin_path = as_str(body.get("pin_path"), label=f"sources[{index}].pin_path")
    pinned = _lookup(pins, pin_path)
    if not isinstance(pinned, str) or not pinned:
        return Finding(name, "outdated", "pin is missing")
    if upstream != pinned:
        return Finding(name, "outdated", f"upstream {upstream} != pin {pinned}")
    return Finding(name, "current", f"matches upstream {upstream}")


def _model_retirement_finding(
    document: Mapping[str, object],
    *,
    retired_model_ids: Sequence[str],
    timeout: float,
) -> Finding:
    pins = pins_of(document)
    models = pins.get("model_ids")
    if not isinstance(models, list) or not all(isinstance(item, str) for item in models):
        return Finding("model_deprecation", "outdated", "model_ids pin is missing")
    pinned_ids = [str(item) for item in models]
    supplied = [model for model in retired_model_ids if model in pinned_ids]
    if supplied:
        names = ", ".join(supplied)
        return Finding(
            "model_deprecation",
            "outdated",
            f"caller reported retired model ids: {names}",
        )
    source = _deprecation_source(document)
    if source is None:
        return Finding(
            "model_deprecation",
            "unchecked",
            "no deprecation notice source configured; not guessing",
        )
    loaded = fetch_json(source, timeout=timeout)
    if not isinstance(loaded, dict):
        return Finding(
            "model_deprecation",
            "unchecked",
            "deprecation source could not be read; not guessing",
        )
    retired = loaded.get("retired")
    if not isinstance(retired, list):
        return Finding("model_deprecation", "unchecked", "deprecation source has no retired list")
    retired_names = [item for item in retired if isinstance(item, str)]
    hit = [model for model in pinned_ids if model in retired_names]
    if hit:
        return Finding("model_deprecation", "outdated", "retired: " + ", ".join(hit))
    return Finding("model_deprecation", "current", "pinned model ids are not in the retired list")


def _deprecation_source(document: Mapping[str, object]) -> str | None:
    for index, item in enumerate(as_list(document.get("sources"), label="sources")):
        body = as_mapping(item, label=f"sources[{index}]")
        if body.get("kind") != "deprecation":
            continue
        url = body.get("url")
        if isinstance(url, str) and url:
            return url
        return None
    return None


def _infrastructure_finding(
    flag: bool | None,
    ledger: Mapping[str, object] | None,
) -> Finding:
    from_ledger = infrastructure_failure(ledger)
    if flag is True or from_ledger is True:
        return Finding(
            "infrastructure",
            "outdated",
            "a scheduled run failed for an infrastructure reason",
        )
    if flag is False or from_ledger is False:
        return Finding("infrastructure", "current", "no infrastructure failure was recorded")
    return Finding("infrastructure", "unchecked", "no infrastructure flag or ledger was passed")


def _oracle_finding(
    document: Mapping[str, object],
    *,
    root: Path,
    oracle_failed: bool | None,
    run_self_check: bool,
    work: Path | None,
) -> Finding:
    if oracle_failed is True:
        return Finding("oracle_self_check", "outdated", "oracle unit test failed")
    if oracle_failed is False:
        return Finding("oracle_self_check", "current", "oracle unit test passed (caller flag)")
    if not run_self_check:
        return Finding("oracle_self_check", "unchecked", "oracle self check was not run")
    paths = as_mapping(document.get("paths"), label="paths")
    relative = paths.get("oracle_config")
    if not isinstance(relative, str):
        return Finding("oracle_self_check", "outdated", "oracle config path is missing")
    rules_path = root / relative
    if work is not None:
        passed, detail = oracle_self_check(rules_path, work)
    else:
        with tempfile.TemporaryDirectory(prefix="snowbot-oracle-") as directory:
            passed, detail = oracle_self_check(rules_path, Path(directory))
    if passed:
        return Finding("oracle_self_check", "current", detail)
    return Finding("oracle_self_check", "outdated", detail)


def _flag_finding(name: str, failed: bool | None, *, failed_detail: str, ok: str) -> Finding:
    if failed is None:
        return Finding(name, "unchecked", "not provided; not guessing")
    if failed:
        return Finding(name, "outdated", failed_detail)
    return Finding(name, "current", ok)


def _lookup(document: object, path: str) -> object | None:
    current = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _load_or_default(path: Path | None, version: str) -> dict[str, object]:
    if path is None:
        return default_status(version)
    return load_status(path)


def _proposed(
    status: Mapping[str, object],
    *,
    schedule: str,
    version_state: str,
    reason: str,
    fix_attempts: int,
    signature: str | None,
) -> dict[str, object]:
    if schedule not in {"active", "paused"}:
        schedule = "paused"
    if schedule == "active" and version_state == "outdated":
        schedule = "paused"
    return {
        "schema_version": 1,
        "schedule": schedule,
        "version_state": version_state,
        "kill": False,
        "reason": reason,
        "fix_attempts": fix_attempts,
        "last_drift_signature": signature if signature else None,
        "version": status["version"],
    }
