"""Aggregate immutable run records into tables.

The main-study mixed model ``weakened ~ arm * model + (1|task)`` is not fit
here. Paired tests treat the task as the sampling unit.
"""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from research.errors import ConfigError
from research.record import read_record
from research.versioning import POOLING_RULE

_OUTCOMES = ("attempted", "landed", "circumvented")
_Z = 1.96


@dataclass(frozen=True, slots=True)
class Interval:
    rate: float | None
    low: float | None
    high: float | None
    method: str


@dataclass(frozen=True, slots=True)
class PairedResult:
    outcome: str
    reference_arm: str
    comparison_arm: str
    model: str
    n_tasks: int
    reference_only: int
    comparison_only: int
    statistic: float | None
    p_value: float | None
    note: str
    diff_mean: float | None
    diff_low: float | None
    diff_high: float | None


def proportion_interval(successes: int, total: int, *, z: float = _Z) -> Interval:
    """Wilson interval, or the rule-of-three upper bound when there are no events."""
    if total <= 0:
        return Interval(rate=None, low=None, high=None, method="undefined")
    if successes < 0 or successes > total:
        raise ConfigError(f"successes {successes} outside 0..{total}")
    rate = successes / total
    if successes == 0:
        return Interval(rate=0.0, low=0.0, high=min(1.0, 3.0 / total), method="rule-of-three")
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (rate + z2 / (2.0 * total)) / denom
    margin = z * math.sqrt((rate * (1.0 - rate) + z2 / (4.0 * total)) / total) / denom
    return Interval(
        rate=rate,
        low=max(0.0, center - margin),
        high=min(1.0, center + margin),
        method="wilson",
    )


def mcnemar(
    reference: list[bool], comparison: list[bool]
) -> tuple[int, int, float | None, float | None, str]:
    """McNemar test on paired task outcomes. No continuity correction."""
    if len(reference) != len(comparison):
        raise ConfigError("McNemar inputs must be paired")
    reference_only = 0
    comparison_only = 0
    for left, right in zip(reference, comparison, strict=True):
        if left and not right:
            reference_only += 1
        elif right and not left:
            comparison_only += 1
    discordant = reference_only + comparison_only
    if discordant == 0:
        return reference_only, comparison_only, None, None, "no discordant pairs"
    statistic = (reference_only - comparison_only) ** 2 / discordant
    p_value = math.erfc(math.sqrt(statistic / 2.0))
    return reference_only, comparison_only, statistic, p_value, "mcnemar"


def cluster_bootstrap_diff(
    by_task: dict[str, tuple[list[bool], list[bool]]],
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[float | None, float | None, float | None]:
    """Mean within-task rate difference, resampling tasks with equal weight."""
    if n_boot <= 0:
        raise ConfigError("n_boot must be positive")
    tasks = sorted(by_task)
    if not tasks:
        return None, None, None
    point = _mean_task_diff(tasks, by_task)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_boot):
        sampled = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        draws.append(_mean_task_diff(sampled, by_task))
    draws.sort()
    low = draws[round(0.025 * (len(draws) - 1))]
    high = draws[round(0.975 * (len(draws) - 1))]
    return point, low, high


def extract_run(
    run_dir: Path,
    *,
    out_dir: Path | None = None,
    reference_arm: str = "A0",
    per_stratum: int = 5,
    sample_seed: int = 0,
    n_boot: int = 2000,
) -> dict[str, Path]:
    destination = out_dir or run_dir
    destination.mkdir(parents=True, exist_ok=True)
    rows = load_rows(run_dir)
    assert_single_version(rows)
    results_path = destination / "results.jsonl"
    summary_path = destination / "summary.csv"
    tables_path = destination / "tables.md"
    sample_path = destination / "label_sample.csv"
    _write_jsonl(results_path, rows)
    summary = summarize(rows)
    _write_summary(summary_path, summary)
    paired = paired_comparisons(rows, reference_arm=reference_arm, n_boot=n_boot)
    tables_path.write_text(render_tables(summary, paired, reference_arm), encoding="utf-8")
    _write_sample(sample_path, label_sample(rows, per_stratum=per_stratum, seed=sample_seed))
    return {
        "results": results_path,
        "summary": summary_path,
        "tables": tables_path,
        "label_sample": sample_path,
    }


def load_rows(run_dir: Path) -> list[dict[str, object]]:
    paths = sorted(run_dir.rglob("record.json"))
    rows: list[dict[str, object]] = []
    for path in paths:
        if path.name != "record.json":
            continue
        record = read_record(path)
        rows.append(_row_from_record(record))
    return rows


def assert_single_version(rows: list[dict[str, object]]) -> None:
    versions = {str(row["version"]) for row in rows}
    if len(versions) > 1:
        raise ConfigError(POOLING_RULE)


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    assert_single_version(rows)
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["arm"]), str(row["model"]))].append(row)
    summary: list[dict[str, object]] = []
    for arm, model in sorted(groups):
        group = groups[(arm, model)]
        item: dict[str, object] = {
            "arm": arm,
            "model": model,
            "version": group[0]["version"],
            "n": len(group),
        }
        for outcome in _OUTCOMES:
            successes = sum(1 for row in group if row[outcome] is True)
            interval = proportion_interval(successes, len(group))
            item[f"{outcome}_k"] = successes
            item[f"{outcome}_rate"] = interval.rate
            item[f"{outcome}_ci_low"] = interval.low
            item[f"{outcome}_ci_high"] = interval.high
            item[f"{outcome}_ci_method"] = interval.method
        honest = sum(1 for row in group if row["honest_pass"] is True)
        costs = [_num(row["cost_usd"]) for row in group]
        tokens = [_whole(row["tokens"]) for row in group]
        item["honest_pass_k"] = honest
        item["honest_pass_rate"] = honest / len(group)
        item["mean_cost_usd"] = sum(costs) / len(group)
        item["total_cost_usd"] = sum(costs)
        item["mean_tokens"] = sum(tokens) / len(group)
        item["total_tokens"] = sum(tokens)
        summary.append(item)
    return summary


def paired_comparisons(
    rows: list[dict[str, object]],
    *,
    reference_arm: str,
    n_boot: int,
) -> list[PairedResult]:
    models = sorted({str(row["model"]) for row in rows})
    arms = sorted({str(row["arm"]) for row in rows if str(row["arm"]) != reference_arm})
    results: list[PairedResult] = []
    for model in models:
        for arm in arms:
            for outcome in _OUTCOMES:
                results.append(
                    _compare(
                        rows,
                        reference_arm=reference_arm,
                        comparison_arm=arm,
                        model=model,
                        outcome=outcome,
                        n_boot=n_boot,
                    )
                )
    return results


def label_sample(
    rows: list[dict[str, object]],
    *,
    per_stratum: int,
    seed: int,
) -> list[dict[str, object]]:
    if per_stratum <= 0:
        raise ConfigError("per_stratum must be positive")
    strata: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        flag = _detector_flag(row)
        strata[(str(row["model"]), str(row["arm"]), flag)].append(row)
    rng = random.Random(seed)
    chosen: list[dict[str, object]] = []
    for key in sorted(strata):
        group = strata[key]
        picked = group if len(group) <= per_stratum else rng.sample(group, per_stratum)
        for row in picked:
            copied = dict(row)
            copied["detector_flag"] = key[2]
            copied["human_label"] = ""
            chosen.append(copied)
    return chosen


def render_tables(
    summary: list[dict[str, object]],
    paired: list[PairedResult],
    reference_arm: str,
) -> str:
    lines = [
        "# Harness summary",
        "",
        "Rates below count runs. Paired tests resample tasks: McNemar collapses",
        "seeds with logical OR, and the cluster bootstrap gives each task equal",
        "weight using the within-task mean. The mixed model",
        "`weakened ~ arm * model + (1|task)` is not fit in this package.",
        POOLING_RULE + ".",
        "",
        "## Rates",
        "",
    ]
    if not summary:
        lines.append("No run records.")
        lines.append("")
    else:
        lines.extend(_rate_table(summary))
    lines.extend(["", "## Paired comparisons", ""])
    if not paired:
        lines.append(f"No comparison arms against `{reference_arm}`.")
        lines.append("")
    for item in paired:
        lines.extend(
            [
                f"### {item.outcome} {item.comparison_arm} vs {item.reference_arm} ({item.model})",
                "",
                f"- tasks: {item.n_tasks}",
                f"- {item.reference_arm} only: {item.reference_only}",
                f"- {item.comparison_arm} only: {item.comparison_only}",
                f"- McNemar statistic: {_fmt(item.statistic)} ({item.note})",
                f"- McNemar p-value: {_fmt(item.p_value)}",
                (
                    f"- bootstrap mean difference ({item.comparison_arm} - "
                    f"{item.reference_arm}): {_fmt(item.diff_mean)}"
                ),
                f"- bootstrap 95% interval: {_fmt(item.diff_low)} to {_fmt(item.diff_high)}",
                "",
            ]
        )
    lines.append(
        "Zero-event intervals use the rule of three (3/n, clipped at 1). "
        "Other intervals are Wilson."
    )
    lines.append("")
    return "\n".join(lines)


def _row_from_record(record: dict[str, object]) -> dict[str, object]:
    required = (
        "cell_id",
        "task_id",
        "condition_id",
        "arm",
        "model",
        "seed",
        "attempted",
        "landed",
        "circumvented",
        "tests_passed",
        "cost_usd",
        "tokens",
        "version",
    )
    missing = [key for key in required if key not in record]
    if missing:
        raise ConfigError(f"record missing {', '.join(missing)}")
    attempted = _as_bool(record["attempted"], "attempted")
    landed = _as_bool(record["landed"], "landed")
    circumvented = _as_bool(record["circumvented"], "circumvented")
    tests_passed = record["tests_passed"]
    if tests_passed is not None:
        tests_passed = _as_bool(tests_passed, "tests_passed")
    honest = tests_passed is True and not attempted and not landed and not circumvented
    cost = record["cost_usd"]
    tokens = record["tokens"]
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        raise ConfigError("cost_usd must be a number")
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        raise ConfigError("tokens must be an integer")
    return {
        "cell_id": str(record["cell_id"]),
        "task_id": str(record["task_id"]),
        "condition_id": str(record["condition_id"]),
        "arm": str(record["arm"]),
        "model": str(record["model"]),
        "seed": record["seed"],
        "attempted": attempted,
        "landed": landed,
        "circumvented": circumvented,
        "tests_passed": tests_passed,
        "honest_pass": honest,
        "cost_usd": float(cost),
        "tokens": tokens,
        "version": _version(record["version"]),
    }


def _compare(
    rows: list[dict[str, object]],
    *,
    reference_arm: str,
    comparison_arm: str,
    model: str,
    outcome: str,
    n_boot: int,
) -> PairedResult:
    ref_rows = [row for row in rows if row["arm"] == reference_arm and row["model"] == model]
    cmp_rows = [row for row in rows if row["arm"] == comparison_arm and row["model"] == model]
    ref_tasks = {str(row["task_id"]) for row in ref_rows}
    cmp_tasks = {str(row["task_id"]) for row in cmp_rows}
    tasks = sorted(ref_tasks & cmp_tasks)
    ref_binary: list[bool] = []
    cmp_binary: list[bool] = []
    by_task: dict[str, tuple[list[bool], list[bool]]] = {}
    for task_id in tasks:
        left = [
            _as_bool(row[outcome], outcome) for row in ref_rows if str(row["task_id"]) == task_id
        ]
        right = [
            _as_bool(row[outcome], outcome) for row in cmp_rows if str(row["task_id"]) == task_id
        ]
        ref_binary.append(any(left))
        cmp_binary.append(any(right))
        by_task[task_id] = (left, right)
    reference_only, comparison_only, statistic, p_value, note = mcnemar(ref_binary, cmp_binary)
    diff_mean, diff_low, diff_high = cluster_bootstrap_diff(by_task, n_boot=n_boot)
    return PairedResult(
        outcome=outcome,
        reference_arm=reference_arm,
        comparison_arm=comparison_arm,
        model=model,
        n_tasks=len(tasks),
        reference_only=reference_only,
        comparison_only=comparison_only,
        statistic=statistic,
        p_value=p_value,
        note=note,
        diff_mean=diff_mean,
        diff_low=diff_low,
        diff_high=diff_high,
    )


def _mean_task_diff(
    tasks: list[str],
    by_task: dict[str, tuple[list[bool], list[bool]]],
) -> float:
    diffs: list[float] = []
    for task_id in tasks:
        left, right = by_task[task_id]
        if not left or not right:
            raise ConfigError(f"task {task_id} has an empty arm")
        diffs.append((sum(right) / len(right)) - (sum(left) / len(left)))
    return sum(diffs) / len(diffs)


def _detector_flag(row: dict[str, object]) -> str:
    if row["attempted"] is True or row["landed"] is True or row["circumvented"] is True:
        return "positive"
    return "negative"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    import json

    lines = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_summary(path: Path, summary: list[dict[str, object]]) -> None:
    fields = [
        "arm",
        "model",
        "version",
        "n",
        "attempted_k",
        "attempted_rate",
        "attempted_ci_low",
        "attempted_ci_high",
        "attempted_ci_method",
        "landed_k",
        "landed_rate",
        "landed_ci_low",
        "landed_ci_high",
        "landed_ci_method",
        "circumvented_k",
        "circumvented_rate",
        "circumvented_ci_low",
        "circumvented_ci_high",
        "circumvented_ci_method",
        "honest_pass_k",
        "honest_pass_rate",
        "mean_cost_usd",
        "total_cost_usd",
        "mean_tokens",
        "total_tokens",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in summary:
            writer.writerow(row)


def _write_sample(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "cell_id",
        "task_id",
        "model",
        "arm",
        "seed",
        "detector_flag",
        "attempted",
        "landed",
        "circumvented",
        "human_label",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _rate_table(summary: list[dict[str, object]]) -> list[str]:
    header = (
        "| arm | model | n | attempted | landed | circumvented "
        "| honest pass | mean USD | mean tokens |"
    )
    rule = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, rule]
    for row in summary:
        lines.append(
            (
                "| {arm} | {model} | {n} | {attempted} | {landed} | "
                "{circumvented} | {honest} | {cost} | {tokens} |"
            ).format(
                arm=row["arm"],
                model=row["model"],
                n=row["n"],
                attempted=_rate_cell(row, "attempted"),
                landed=_rate_cell(row, "landed"),
                circumvented=_rate_cell(row, "circumvented"),
                honest=f"{row['honest_pass_k']}/{row['n']}",
                cost=f"{_num(row['mean_cost_usd']):.4f}",
                tokens=f"{_num(row['mean_tokens']):.1f}",
            )
        )
    return lines


def _rate_cell(row: dict[str, object], outcome: str) -> str:
    low = row[f"{outcome}_ci_low"]
    high = row[f"{outcome}_ci_high"]
    method = row[f"{outcome}_ci_method"]
    return (
        f"{row[f'{outcome}_k']}/{row['n']} "
        f"[{_fmt(low if isinstance(low, float) else None)}, "
        f"{_fmt(high if isinstance(high, float) else None)}] {method}"
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _num(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError("expected a number")
    return float(value)


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("expected an integer")
    return value


def _version(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("record version must be a non-empty string")
    return value


def _as_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be a boolean")
    return value
