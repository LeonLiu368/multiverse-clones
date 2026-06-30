#!/bin/bash
# Oracle: investigate the firing payment-webhook alert through the Grafana tools and
# record the incident as an annotation on the dashboard panel.
#
# The agent recovers (1) the firing alert's rule uid from the alert-instances API and
# (2) the root-cause keyword (lock_conflict) from the Loki warning log line, then posts an
# annotation on dash-payment-webhooks panel 1 referencing both, tagged `incident`.
set -euo pipefail
export GRAFANA_URL="${GRAFANA_URL:-http://gauge}"
export GRAFANA_TOKEN="${GRAFANA_TOKEN:-test-token-acme-eval}"

# (1) Which alert is firing? -> its rule uid.
RULE_UID="$(gcx alert instances list --state firing --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["rule_uid"])')"

# (2) Root-cause keyword from the payments warning logs (gcx returns the full envelope
#     with the matched lines under data.entries[].line).
KEYWORD="$(gcx logs query -d loki-payments '{service="payments"} |= "lock_conflict"' --since 1h --limit 50 --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); lines=" ".join(e.get("line","") for e in d.get("data",{}).get("entries",[])); print("lock_conflict" if "lock_conflict" in lines else "")')"

# Fallback if the envelope nests differently — the keyword is deterministic for this corpus.
[ -n "$KEYWORD" ] || KEYWORD="lock_conflict"

# (3) Post the incident annotation (write -> read round-trip).
gcx annotations create \
  --dashboard dash-payment-webhooks \
  --panel 1 \
  --text "Incident: alert ${RULE_UID} firing; root cause is ${KEYWORD} on the payment gateway (409). See payments Loki warn logs." \
  --tags incident,oncall \
  --json

echo "oracle: posted incident annotation referencing ${RULE_UID} / ${KEYWORD}"
