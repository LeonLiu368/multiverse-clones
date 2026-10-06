#!/bin/bash
# Oracle for the LOAD-BEARING variant. The webhook controls AND the exact configuration interface
# (the PAPERLESS_WEBHOOKS_* setting names) live ONLY in gauge — not in the instruction. Recover the
# spec from the incident logs first and abort if it is not reachable: this is the load-bearing
# self-test. Delete the gcx query block below and the oracle can no longer derive the fix -> reward 0.
set -euo pipefail
cd /app/repo
git config --global --add safe.directory /app/repo 2>/dev/null || true

echo "[oracle] recovering INC-4471 webhook controls from gauge ..."
INC="$(gcx logs query '{service="paperless-ngx"} |= "INC-4471"' 2>/dev/null || true)"
echo "$INC" | grep -q "PAPERLESS_WEBHOOKS_ALLOWED_SCHEMES" \
  && echo "$INC" | grep -q "PAPERLESS_WEBHOOKS_ALLOWED_PORTS" \
  && echo "$INC" | grep -q "PAPERLESS_WEBHOOKS_ALLOW_INTERNAL_REQUESTS" \
  || { echo "[oracle] FAIL: webhook control spec not recoverable from gauge — cannot derive the fix"; exit 1; }
echo "[oracle] recovered controls + config interface from gauge incident logs."

git apply /solution/golden.patch || patch -p1 < /solution/golden.patch
echo "applied golden.patch for paperless-ngx-10555-lb"
