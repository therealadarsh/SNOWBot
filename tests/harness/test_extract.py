"""Extract statistics from real record files."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from research.errors import ConfigError, HashMismatch
from research.extract import (
    cluster_bootstrap_diff,
    extract_run,
    label_sample,
    load_rows,
    mcnemar,
    proportion_interval,
)
from research.record import read_record, write_record


def test_wilson_and_rule_of_three() -> None:
    interval = proportion_interval(81, 100)
    assert interval.method == "wilson"
    assert interval.low is not None and abs(interval.low - 0.7222) < 0.01
    assert interval.high is not None and abs(interval.high - 0.8749) < 0.01
    zero = proportion_interval(0, 10)
    assert zero.method == "rule-of-three"
    assert zero.low == 0.0
    assert zero.high == pytest.approx(0.3)
    assert proportion_interval(0, 1).high == 1.0
    assert proportion_interval(0, 0).method == "undefined"
    with pytest.raises(ConfigError):
        proportion_interval(2, 1)


def test_mcnemar_and_bootstrap() -> None:
    reference_only, comparison_only, statistic, p_value, note = mcnemar(
        [True, True, True, False],
        [False, False, False, True],
    )
    assert (reference_only, comparison_only, note) == (3, 1, "mcnemar")
    assert statistic == pytest.approx(1.0)
    assert p_value == pytest.approx(math.erfc(math.sqrt(0.5)))
    empty = mcnemar([True, False], [True, False])
    assert empty[2] is None
    assert empty[4] == "no discordant pairs"
    point, low, high = cluster_bootstrap_diff(
        {"t1": ([False], [True]), "t2": ([False], [True])},
        n_boot=30,
        seed=1,
    )
    assert point == pytest.approx(1.0)
    assert low == pytest.approx(1.0)
    assert high == pytest.approx(1.0)
    again = cluster_bootstrap_diff(
        {
            "t1": ([False, True], [True, True]),
            "t2": ([False, False], [False, True]),
        },
        n_boot=40,
        seed=2,
    )
    repeat = cluster_bootstrap_diff(
        {
            "t1": ([False, True], [True, True]),
            "t2": ([False, False], [False, True]),
        },
        n_boot=40,
        seed=2,
    )
    assert again == repeat
    assert cluster_bootstrap_diff({}, n_boot=5) == (None, None, None)


def _record(cell: str, arm: str, task: str, **flags: object) -> dict[str, object]:
    return {
        "cell_id": cell,
        "task_id": task,
        "condition_id": arm,
        "arm": arm,
        "model": "haiku",
        "seed": flags.get("seed", 1),
        "attempted": flags.get("attempted", False),
        "landed": flags.get("landed", False),
        "circumvented": flags.get("circumvented", False),
        "tests_passed": flags.get("tests_passed", True),
        "cost_usd": flags.get("cost_usd", 0.5),
        "tokens": flags.get("tokens", 10),
        "provider_calls": 0,
        "version": flags.get("version", "0.1.0"),
    }


def test_extract_tables_and_negative_sample(tmp_path: Path) -> None:
    run = tmp_path / "run"
    write_record(run / "a", _record("a", "A0", "t1", tests_passed=True))
    write_record(
        run / "b",
        _record("b", "A1", "t1", landed=True, attempted=True, tests_passed=False, seed=1),
    )
    write_record(
        run / "c",
        _record("c", "A1", "t1", landed=True, attempted=True, tests_passed=False, seed=2),
    )
    write_record(run / "d", _record("d", "A1", "t2", circumvented=True, tests_passed=True))
    paths = extract_run(run, n_boot=50, per_stratum=5)
    rows = load_rows(run)
    assert len(rows) == 4
    assert rows[0]["honest_pass"] is True
    assert rows[0]["version"] == "0.1.0"
    text = paths["tables"].read_text(encoding="utf-8")
    assert "results from different versions are never pooled" in text
    assert "rule of three" in text
    assert "A1 vs A0" in text
    assert "weakened ~ arm * model + (1|task)" in text
    summary = paths["summary"].read_text(encoding="utf-8")
    assert "honest_pass_k" in summary
    assert "rule-of-three" in summary or "wilson" in summary
    sample = paths["label_sample"].read_text(encoding="utf-8")
    assert "negative" in sample
    assert "positive" in sample
    assert "human_label" in sample
    sampled = label_sample(rows, per_stratum=1, seed=0)
    flags = {str(row["detector_flag"]) for row in sampled}
    assert "negative" in flags
    assert "positive" in flags


def test_extract_empty_and_bad_record(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    paths = extract_run(empty)
    assert "No run records." in paths["tables"].read_text(encoding="utf-8")
    assert paths["results"].read_text(encoding="utf-8") == ""
    record = write_record(tmp_path / "cell", _record("z", "A0", "t"))
    record.chmod(0o644)
    record.write_text(record.read_text(encoding="utf-8") + " \n", encoding="utf-8")
    with pytest.raises(HashMismatch):
        read_record(record)
    with pytest.raises(HashMismatch):
        load_rows(tmp_path / "cell")


def test_results_from_different_versions_are_not_pooled(tmp_path: Path) -> None:
    run = tmp_path / "mixed"
    write_record(run / "a", _record("a", "A0", "t1", version="0.1.0"))
    write_record(run / "b", _record("b", "A0", "t1", version="0.2.0"))
    with pytest.raises(ConfigError, match="never pooled"):
        extract_run(run)
    missing = dict(_record("c", "A0", "t1"))
    del missing["version"]
    write_record(tmp_path / "missing", missing)
    with pytest.raises(ConfigError, match="version"):
        load_rows(tmp_path / "missing")
