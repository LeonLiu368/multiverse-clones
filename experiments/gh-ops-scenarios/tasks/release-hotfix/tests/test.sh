#!/usr/bin/env bash
# Verifier for release-hotfix.
# Reward 1 iff: billing.py on release-v1.1 is fixed (calculate_tax(100,8)==8),
# a PR targeting release-v1.1 is merged, v1.1.1 release exists, issue #1 closed.
set -uo pipefail
mkdir -p /logs/verifier

R=acme/billing
py() { python3 -c "$1" 2>/dev/null || echo 0; }

# 1. billing.py on release-v1.1 must be fixed (no "* 100" bug)
content=$(gh api "repos/$R/contents/billing.py?ref=release-v1.1" 2>/dev/null \
  | py 'import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d["content"]).decode())')

# Write to a temp file and test the function
echo "$content" > /tmp/billing_check.py
fixed=$(python3 - <<'PYEOF'
import sys
sys.path.insert(0, '/tmp')
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("billing_check", "/tmp/billing_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.calculate_tax(100, 8)
    print(1 if abs(result - 8.0) < 0.01 else 0)
except Exception as e:
    print(0)
PYEOF
)

# 2. A PR targeting release-v1.1 must be merged
merged=$(gh api "repos/$R/pulls?state=closed&base=release-v1.1" 2>/dev/null \
  | py 'import sys,json; xs=json.load(sys.stdin); print(int(any(x.get("merged") for x in xs)))')

# 3. v1.1.1 release must exist
release=$(gh api "repos/$R/releases/tags/v1.1.1" 2>/dev/null \
  | py 'import sys,json; d=json.load(sys.stdin); print(int("id" in d))' || echo 0)

# 4. Issue #1 must be closed
issue_closed=$(gh api "repos/$R/issues/1" 2>/dev/null \
  | py 'import sys,json; print(int(json.load(sys.stdin).get("state")=="closed"))' || echo 0)

ok=0
[ "$fixed" = 1 ] && [ "$merged" = 1 ] && [ "$release" = 1 ] && [ "$issue_closed" = 1 ] && ok=1
echo $ok > /logs/verifier/reward.txt
echo "billing_fixed=$fixed pr_merged=$merged v1.1.1_exists=$release issue_closed=$issue_closed -> $ok"
