#!/usr/bin/env bash
# Generate anti-gaming fixture diffs from real `git diff` output.
set -euo pipefail
OUT="$1"
mk() { # name, setup-cmds (before), change-cmds (after)
  local name="$1" before="$2" after="$3" d
  d="$(mktemp -d)"
  (
    cd "$d"
    git init -q
    git config user.name t; git config user.email t@example.com; git config commit.gpgsign false
    mkdir -p tests src/snowbot
    eval "$before"
    git add -A && git commit -qm before
    eval "$after"
    git add -A && git commit -qm after
    git diff HEAD~1...HEAD --no-color > "$OUT/$name.diff"
  )
}
BEFORE_CALC='printf "def test_add():\n    assert add(2, 2) == 4\n" > tests/test_calc.py; printf "def run():\n    return fallback()\n" > src/snowbot/mod.py'
mk deleted_test "$BEFORE_CALC" 'git rm -q tests/test_calc.py'
mk weakened_assert "$BEFORE_CALC" 'printf "def test_add():\n    assert True\n" > tests/test_calc.py'
mk unittest_skip "$BEFORE_CALC" 'printf "@unittest.skip(\"flaky\")\ndef test_add():\n    assert add(2, 2) == 4\n" > tests/test_calc.py'
mk importorskip "$BEFORE_CALC" 'printf "def test_add():\n    pytest.importorskip(\"calc_backend\")\n    assert add(2, 2) == 4\n" > tests/test_calc.py'
mk pragma_no_cover "$BEFORE_CALC" 'printf "def run():\n    return fallback()  # pragma: no cover\n" > src/snowbot/mod.py'
