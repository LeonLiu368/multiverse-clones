#!/usr/bin/env bash
# Oracle: (1) implement should_page per the agreed paging policy from the #incidents
# postmortem, and (2) communicate — post the root cause + new policy to #postmortems.
set -euo pipefail

cat > /workspace/monitoring/alerts.py <<'PY'
"""On-call paging decision (implemented per the agreed post-incident policy)."""


def should_page(error_rate: float, consecutive_breaches: int) -> bool:
    # Critical fast-path: page immediately on a single breach at >=25% error rate.
    if error_rate >= 0.25 and consecutive_breaches >= 1:
        return True
    # Sustained breach: page after >=3 consecutive breaches at >=5%.
    if error_rate >= 0.05 and consecutive_breaches >= 3:
        return True
    return False
PY

# Action beyond coding: post the postmortem to #postmortems via the Slack Web API.
curl -s -X POST "${SLACK_API_URL}/api/chat.postMessage" \
  -H "Authorization: Bearer ${SLACK_BOT_TOKEN}" \
  --data-urlencode "channel=postmortems" \
  --data-urlencode "text=ROOT CAUSE: the pager-fatigue incident was caused by should_page firing on a single transient breach at a low 5% threshold with no sustained-breach requirement, so brief self-resolving spikes paged on-call (the DB connection blip was a red herring). Fix / new policy: page only after >=3 consecutive breaches at >=5% error rate, with a critical fast-path to page immediately at >=25%; below 5% never pages." >/dev/null

echo "oracle: implemented should_page and posted the postmortem to #postmortems"
