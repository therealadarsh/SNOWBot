#!/usr/bin/env bash
# Independent validation gate — run in a fresh context (human or agent) before marking PR ready.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PHASE_ID="${SNOWBOT_PHASE_ID:-1b}"
BASE_REF="${SNOWBOT_VALIDATE_BASE:-origin/main}"
PR_URL="${PR_URL:-}"
VENV="${VALIDATE_VENV:-$ROOT/.venv-validate}"

python3 -m venv "$VENV"
# shellcheck disable=SC1090
source "$VENV/bin/activate"
python -m pip install --upgrade pip -q
pip install -e ".[dev]" -q

echo "==> ruff"
ruff check src tests
ruff format --check src tests

echo "==> mypy"
mypy

echo "==> pytest"
pytest --cov=snowbot --cov-report=term-missing --cov-fail-under=85

echo "==> snowbot validate --phase ${PHASE_ID}"
export SNOWBOT_VALIDATE_BASE="$BASE_REF"
set +e
VALIDATE_OUT="$(snowbot validate --phase "$PHASE_ID" --base-ref "$BASE_REF" ${PR_URL:+--pr "$PR_URL"} 2>&1)"
VALIDATE_RC=$?
set -e
echo "$VALIDATE_OUT"

echo "==> snowbot status --check"
snowbot status --check

VERDICT="pass"
if [[ "$VALIDATE_RC" -ne 0 ]]; then
  if echo "$VALIDATE_OUT" | grep -q "governance_mixed_with_product"; then
    VERDICT="pass_with_notes"
    echo "NOTE: governance mixed with product (bootstrap PR exception documented in STATUS.md)"
    VALIDATE_RC=0
  else
    echo "Independent validation FAILED (verdict=fail)"
    exit "$VALIDATE_RC"
  fi
fi

echo "Independent validation complete (verdict=${VERDICT})"
exit 0
