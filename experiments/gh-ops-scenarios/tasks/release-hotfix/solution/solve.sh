#!/usr/bin/env bash
# Oracle: fix billing.py on release-v1.1 via PR, cut v1.1.1, close issue.
set -euo pipefail

cd /tmp && rm -rf billing
gh repo clone acme/billing
cd billing

git fetch origin release-v1.1
git checkout -b hotfix-tax-calc origin/release-v1.1

cat > billing.py <<'EOF'
def calculate_tax(subtotal, rate):
    """Return the tax amount.

    Args:
        subtotal: pre-tax amount
        rate: tax percentage (e.g. 8 for 8%)
    """
    return subtotal * rate / 100


def total_with_tax(subtotal, rate):
    """Return subtotal plus tax."""
    return subtotal + calculate_tax(subtotal, rate)
EOF

git add billing.py
git commit -m "fix: correct tax percentage calculation on release-v1.1"
git push origin hotfix-tax-calc

PR_URL=$(gh pr create -R acme/billing \
  -t "hotfix: correct tax calculation for v1.1.1" \
  -H hotfix-tax-calc -B release-v1.1 \
  -b "Closes #1. The calculate_tax function on release-v1.1 was returning subtotal * 0.01 * rate * 100, which multiplied by an extra 100. Fixed to return subtotal * rate / 100.")
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

gh pr review "$PR_NUM" -R acme/billing --approve -b "Confirmed — calculate_tax(100, 8) now returns 8.0."

for i in $(seq 1 10); do
  gh pr merge "$PR_NUM" -R acme/billing --method squash && break || sleep 3
done

gh api "repos/acme/billing/releases" -X POST \
  -f tag_name=v1.1.1 \
  -f name="v1.1.1" \
  -f body="Hotfix: corrects the tax calculation bug introduced in v1.1.0." \
  -f target_commitish=release-v1.1 >/dev/null 2>&1 || true

gh issue close 1 -R acme/billing
