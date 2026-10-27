#!/usr/bin/env bash
# Apply recommended branch protection to main (requires gh CLI + admin token).
# Usage: REPO=therealadarsh/SNOWBot ./scripts/apply_branch_protection.sh
set -euo pipefail

REPO="${REPO:-therealadarsh/SNOWBot}"
BRANCH="${BRANCH:-main}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 1
fi

echo "Applying branch protection to ${REPO}@${BRANCH} (dry-run payload shown; uncomment gh call to apply)."

cat <<EOF
Suggested gh api payload:
  required_pull_request_reviews: { required_approving_review_count: 1 }
  required_status_checks: { strict: true, contexts: ["test"] }
  enforce_admins: false
  restrictions: null
EOF

# Uncomment after review:
# gh api \
#   -X PUT \
#   -H "Accept: application/vnd.github+json" \
#   "/repos/${REPO}/branches/${BRANCH}/protection" \
#   -f required_status_checks[strict]=true \
#   -f required_status_checks[contexts][]=test \
#   -f enforce_admins=false \
#   -f required_pull_request_reviews[required_approving_review_count]=1 \
#   -f restrictions=

echo "No changes applied (safe default). Edit script to enable gh api call."
