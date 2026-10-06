#!/usr/bin/env bash
# Seed: acme/billing with a broken billing.py on release-v1.1 (main is fixed).
# The agent must fix release-v1.1 via PR, cut v1.1.1, and close the blocker.
set -uo pipefail

R=acme/billing

gh repo create "$R" -d "billing service" >/dev/null 2>&1 || true

# 1. Seed broken billing.py as the first commit on main
BROKEN=$(printf 'def calculate_tax(subtotal, rate):\n    """Return the tax amount.\n\n    Args:\n        subtotal: pre-tax amount\n        rate: tax percentage (e.g. 8 for 8%%)\n    """\n    # BUG: multiplied by an extra 100 — 8%% becomes 800%%\n    return subtotal * 0.01 * rate * 100\n\n\ndef total_with_tax(subtotal, rate):\n    """Return subtotal plus tax."""\n    return subtotal + calculate_tax(subtotal, rate)\n' | base64 -w0)

gh api "repos/$R/contents/billing.py" -X POST \
  -f content="$BROKEN" \
  -f message="add billing module" \
  -f branch=main >/dev/null 2>&1 || true

# 2. Create the release-v1.1 branch at this broken commit
SHA=$(gh api "repos/$R/git/refs/heads/main" --jq '.object.sha')
gh api "repos/$R/git/refs" -X POST \
  -f ref="refs/heads/release-v1.1" -f sha="$SHA" >/dev/null 2>&1 || true

# 3. Fix main (correct billing.py) — release-v1.1 stays broken
FIXED=$(printf 'def calculate_tax(subtotal, rate):\n    """Return the tax amount.\n\n    Args:\n        subtotal: pre-tax amount\n        rate: tax percentage (e.g. 8 for 8%%)\n    """\n    return subtotal * rate / 100\n\n\ndef total_with_tax(subtotal, rate):\n    """Return subtotal plus tax."""\n    return subtotal + calculate_tax(subtotal, rate)\n' | base64 -w0)

FILE_SHA=$(gh api "repos/$R/contents/billing.py" --jq '.sha')
gh api "repos/$R/contents/billing.py" -X PUT \
  -f content="$FIXED" \
  -f message="fix: correct tax percentage calculation on main" \
  -f sha="$FILE_SHA" \
  -f branch=main >/dev/null 2>&1 || true

# 4. Cut a pre-release v1.1.0 pointing at release-v1.1
gh api "repos/$R/releases" -X POST \
  -f tag_name=v1.1.0 \
  -f name="v1.1.0 (pre-release — pending hotfix)" \
  -f body="Release v1.1.0. NOTE: a critical tax-calculation bug was found after tagging. A v1.1.1 hotfix is pending." \
  -F prerelease=true \
  -f target_commitish=release-v1.1 >/dev/null 2>&1 || true

# 5. Open the blocker issue
gh issue create -R "$R" \
  -t "Release blocker: tax calculation off by 100x on release-v1.1" \
  -b "The \`calculate_tax\` function on the \`release-v1.1\` branch has a bug — it multiplies by an extra 100, so 8% tax on \$100.00 returns \$800.00 instead of \$8.00:

\`\`\`python
>>> calculate_tax(100, 8)
800.0   # should be 8.0
\`\`\`

The fix is already on \`main\` (\`return subtotal * rate / 100\`). Apply the same fix to \`release-v1.1\` via a hotfix PR, then cut a \`v1.1.1\` patch release." \
  >/dev/null 2>&1 || true
