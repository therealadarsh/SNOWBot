from __future__ import annotations

import pytest

from snowbot.runner.policy import (
    is_agent_config,
    is_tool_config,
    stage1_violations,
    stage2_violations,
)


def test_stage1_allows_only_tests() -> None:
    assert stage1_violations([("A", "tests/test_x.py")]) == []
    assert stage1_violations([("M", "tests/test_x.py")]) == []
    assert stage1_violations([("M", "src/snowbot/cli.py")]) == [
        "M src/snowbot/cli.py: stage 1 may only add or change tests/"
    ]
    assert stage1_violations([("D", "tests/test_x.py")]) == [
        "D tests/test_x.py: stage 1 may only add or change tests/"
    ]


def test_stage2_blocks_locked_and_existing_tests() -> None:
    v = stage2_violations(
        [
            ("M", "tests/test_cli.py"),
            ("A", "tests/test_new.py"),
            ("M", "tests/test_issue_7.py"),
            ("A", ".snowbot/locks/issue-7.json"),
            ("M", ".github/workflows/ci.yml"),
            ("M", "pyproject.toml"),
            ("M", "src/snowbot/cli.py"),
        ],
        locked={"tests/test_issue_7.py"},
    )
    assert [s.split(":")[0] for s in v] == [
        "M tests/test_cli.py",
        "M tests/test_issue_7.py",
        "A .snowbot/locks/issue-7.json",
        "M .github/workflows/ci.yml",
        "M pyproject.toml",
    ]


def test_stage2_blocks_deleted_test() -> None:
    assert stage2_violations([("D", "tests/test_cli.py")], set()) == [
        "D tests/test_cli.py: existing test deleted"
    ]


def test_stage2_blocks_any_github_path() -> None:
    v = stage2_violations([("A", ".github/CODEOWNERS"), ("M", ".github/dependabot.yml")], set())
    assert [s.split(":")[0] for s in v] == ["A .github/CODEOWNERS", "M .github/dependabot.yml"]


def test_stage2_blocks_governance_and_config() -> None:
    v = stage2_violations(
        [("M", "AGENTS.md"), ("M", "snowbot.yaml"), ("M", "src/snowbot/validator/x.py")], set()
    )
    assert len(v) == 3


def test_stage2_allows_product_code() -> None:
    assert stage2_violations([("M", "src/snowbot/cli.py"), ("A", "tests/test_new.py")], set()) == []


AGENT_CONFIG_PATHS = [
    "tests/CLAUDE.md",
    "tests/.claude/settings.json",
    "tests/conftest.py",
    "CLAUDE.md",
    ".claude/settings.json",
    ".mcp.json",
    "src/x/AGENTS.md",
    "a/.Cursor/rules",
    "a/.codex/x",
    "x/claude.local.md",
]


@pytest.mark.parametrize("path", AGENT_CONFIG_PATHS)
def test_agent_config_blocked_in_both_stages(path: str) -> None:
    assert is_agent_config(path)
    assert stage1_violations([("A", path)]) == [f"A {path}: agent config"]
    assert stage2_violations([("A", path)], set()) == [f"A {path}: agent config"]


def test_is_agent_config_negatives() -> None:
    assert not is_agent_config("src/snowbot/claude_helper.py")
    assert not is_agent_config("tests/test_x.py")


@pytest.mark.parametrize(
    "path",
    [
        ".GitHub/workflows/x.yml",
        "requirements-dev.txt",
        "sub/requirements.txt",
        "uv.lock",
        "package-lock.json",
        "setup.cfg",
        "tox.ini",
        ".coveragerc",
        "pytest.ini",
        "scripts/x.sh",
        ".snowbot/memory/PLAYBOOK.md",
        "pyproject.toml",
    ],
)
def test_stage2_blocks_more_governance(path: str) -> None:
    assert len(stage2_violations([("M", path)], set())) == 1


# Flipped (C3, ruling R17): these lookalikes are no longer allowed. They are still not
# mistaken for CI or project config; the allowlist or the tool-config rule blocks them.
@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (".githubfoo/x", "outside allowed paths"),
        ("sub/pyproject.toml", "tool config"),
        ("sub/snowbot.yaml", "outside allowed paths"),
    ],
)
def test_stage2_lookalikes(path: str, reason: str) -> None:
    assert stage2_violations([("M", path)], set()) == [f"M {path}: {reason}"]


TOOL_CONFIG_PATHS = [
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "pytest.ini",
    ".pytest.ini",
    "mypy.ini",
    ".mypy.ini",
    "ruff.toml",
    ".ruff.toml",
    ".coveragerc",
    "sitecustomize.py",
    "usercustomize.py",
    "src/snowbot/x/pyproject.toml",
    "src/sitecustomize.py",
    "src/snowbot/usercustomize.py",
    "src/evil.pth",
    "docs/Mypy.INI",
    "tests/PyProject.toml",
]


@pytest.mark.parametrize("path", TOOL_CONFIG_PATHS)
def test_tool_config_blocked_in_stage2(path: str) -> None:
    assert is_tool_config(path)
    assert stage2_violations([("A", path)], set()) == [f"A {path}: tool config"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/pytest.ini",
        "tests/pyproject.toml",
        "tests/ruff.toml",
        "tests/sub/setup.cfg",
        "tests/sitecustomize.py",
        "tests/x.pth",
        "tests/.coveragerc",
        "tests/mypy.ini",
    ],
)
def test_tool_config_blocked_in_stage1(path: str) -> None:
    assert stage1_violations([("A", path)]) == [f"A {path}: tool config"]
    assert stage1_violations([("M", path)]) == [f"M {path}: tool config"]


def test_conftest_keeps_agent_config_reason() -> None:
    assert is_tool_config("tests/conftest.py")
    assert stage1_violations([("A", "tests/conftest.py")]) == ["A tests/conftest.py: agent config"]


def test_is_tool_config_negatives() -> None:
    for path in ["src/snowbot/setup_helper.py", "tests/test_pyproject.py", "docs/ruff.md"]:
        assert not is_tool_config(path)


@pytest.mark.parametrize("status", ["T", "D", "R", "C", "X"])
def test_stage1_rejects_non_add_modify_status(status: str) -> None:
    assert stage1_violations([(status, "tests/test_x.py")]) == [
        f"{status} tests/test_x.py: stage 1 may only add or change tests/"
    ]


def test_stage2_type_change_on_existing_test_blocked() -> None:
    assert stage2_violations([("T", "tests/test_cli.py")], set()) == [
        "T tests/test_cli.py: existing test changed"
    ]


@pytest.mark.parametrize(
    "path",
    [
        "src/mypy/__main__.py",
        "src/mypy/__init__.py",
        "ruff/__main__.py",
        "pytest/__init__.py",
        "setup_helper.py",
        "evil.py",
        "src/other_pkg/x.py",
        "src/snowbot_shadow.py",
        "src/x.py",
        "scripts/new.py",
        ".snowbot/x",
        "Makefile",
        "noxfile.py",
        ".gitignore",
        "README.rst",
        "infra/app.py",
    ],
)
def test_stage2_blocks_paths_outside_allowlist(path: str) -> None:
    reasons = [v.split(": ", 1)[1] for v in stage2_violations([("A", path)], set())]
    assert len(reasons) == 1
    assert reasons[0] in {"outside allowed paths", "scripts", "snowbot state"}


def test_stage2_shadow_modules_report_outside_allowed_paths() -> None:
    assert stage2_violations(
        [("A", "src/mypy/__main__.py"), ("A", "ruff/__main__.py"), ("A", "setup_helper.py")],
        set(),
    ) == [
        "A src/mypy/__main__.py: outside allowed paths",
        "A ruff/__main__.py: outside allowed paths",
        "A setup_helper.py: outside allowed paths",
    ]
    assert stage2_violations([("A", "src/sitecustomize.py")], set()) == [
        "A src/sitecustomize.py: tool config"
    ]


@pytest.mark.parametrize(
    "path",
    [
        "src/snowbot/new_mod.py",
        "src/snowbot/runner/x.py",
        "docs/guide.md",
        "docs/adr/0009-x.md",
        "examples/app/main.py",
        "README.md",
        "CHANGELOG.md",
        "STATUS.md",
        "tests/test_new.py",
        "tests/runner/test_new.py",
    ],
)
def test_stage2_allowlist_allows(path: str) -> None:
    assert stage2_violations([("A", path)], set()) == []


def test_stage2_allowed_root_files_may_be_modified() -> None:
    changes = [("M", "README.md"), ("M", "CHANGELOG.md"), ("M", "STATUS.md")]
    assert stage2_violations(changes, set()) == []
    assert stage2_violations([("M", "src/snowbot/cli.py"), ("D", "src/snowbot/x.py")], set()) == []


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("Src/Snowbot/Validator/x.py", "governance path"),
        ("SRC/SNOWBOT/TEMPLATES/t.j2", "governance path"),
        ("Docs/ARCHITECT_GATE.md", "governance path"),
        ("agents.MD", "agent config"),
        ("Scripts/x.sh", "scripts"),
        (".SNOWBOT/locks/issue-1.json", "lock manifest"),
        ("SnowBot.yaml", "project config"),
        ("Requirements-Dev.TXT", "build or tool config"),
        ("TESTS/test_cli.py", "existing test modified"),
    ],
)
def test_stage2_comparisons_are_case_insensitive(path: str, reason: str) -> None:
    assert stage2_violations([("M", path)], set()) == [f"M {path}: {reason}"]


def test_stage2_locked_test_case_insensitive() -> None:
    assert stage2_violations([("A", "Tests/Test_Issue_7.py")], {"tests/test_issue_7.py"}) == [
        "A Tests/Test_Issue_7.py: locked test"
    ]


@pytest.mark.parametrize(
    "path",
    [
        "tests/snowbot/__init__.py",
        "tests/runner/snowbot.py",
        "tests/pytest/__init__.py",
        "tests/json.py",
        "tests/yaml/__init__.py",
    ],
)
def test_tests_cannot_add_shadow_modules(path: str) -> None:
    # tests/ has no __init__.py, so pytest's prepend import mode puts test directories at
    # the front of sys.path: a tests/snowbot package would replace the real one.
    msg = stage1_violations([("A", path)])
    assert len(msg) == 1 and "shadows module" in msg[0]
    msg = stage2_violations([("A", path)], set())
    assert len(msg) == 1 and "shadows module" in msg[0]


def test_existing_test_tree_has_no_shadow_false_positives() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = [p.relative_to(root).as_posix() for p in (root / "tests").rglob("*.py")]
    files = [f for f in files if "__pycache__" not in f and not f.endswith("conftest.py")]
    assert files
    assert [v for v in stage1_violations([("M", f) for f in files]) if "shadows" in v] == []


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("src/sitecustomize.pyc", "tool config"),
        ("src/usercustomize.cpython-312-darwin.so", "tool config"),
        ("src/evil.egg-info/entry_points.txt", "package metadata"),
        ("src/snowbot/x.dist-info/METADATA", "package metadata"),
        ("tests/snowbot.pyc", "shadows module 'snowbot'"),
        ("src/mypy/__init__.pyc", "outside allowed paths"),
    ],
)
def test_stage2_blocks_compiled_and_metadata_plants(path: str, reason: str) -> None:
    assert stage2_violations([("A", path)], set()) == [f"A {path}: {reason}"]
