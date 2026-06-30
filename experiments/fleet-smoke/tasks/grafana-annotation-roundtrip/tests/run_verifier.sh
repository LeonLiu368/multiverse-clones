#!/bin/bash
# Deterministic verification for gauge-annotation-roundtrip.
#
# reward=1 iff the agent created an annotation, READ BACK through the Grafana API, that:
#   * is anchored to dashboard dash-payment-webhooks, panel 1,
#   * is tagged `incident`,
#   * references the firing alert's rule uid (alert-payment-retry-burn), AND
#   * names the root-cause keyword recovered from the Loki logs (lock_conflict).
#
# Everything is read back over HTTP — narration is never trusted. The seed corpus ships
# zero annotations, so a nop run reads back none and scores 0.
set -uo pipefail
mkdir -p /logs/verifier
API="${GRAFANA_URL:-http://grafana}"
TOKEN="${GRAFANA_TOKEN:-test-token-acme-eval}"
KEY="dash-payment-webhooks"

annotations_json="$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/api/annotations?dashboardUID=$KEY" || echo '[]')"

reward="$(python3 - "$annotations_json" <<'PY'
import json, sys
try:
    items = json.loads(sys.argv[1])
except Exception:
    print(0); raise SystemExit
if not isinstance(items, list):
    print(0); raise SystemExit

RULE_UID = "alert-payment-retry-burn"
KEYWORD = "lock_conflict"

ok = False
for a in items:
    text = str(a.get("text", "")).lower()
    tags = [str(t).lower() for t in (a.get("tags") or [])]
    panel = a.get("panelId", a.get("panel_id"))
    try:
        panel_ok = int(panel) == 1
    except (TypeError, ValueError):
        panel_ok = False
    if (
        panel_ok
        and "incident" in tags
        and RULE_UID.lower() in text
        and KEYWORD in text
    ):
        ok = True
        break
print(1 if ok else 0)
PY
)"

echo "[verifier] annotations_read_back=$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' <<<"$annotations_json" 2>/dev/null || echo '?')"
echo "[verifier] reward=$reward"
echo "$reward" > /logs/verifier/reward.txt
exit 0
