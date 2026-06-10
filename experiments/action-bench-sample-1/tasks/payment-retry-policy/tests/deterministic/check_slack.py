import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from workflow_assertions import any_pr_reference, select_incident_pr

REPO = 'acme/payment-retry-policy'
ISSUE = 'OPS-501'
TOPIC_TERMS = ['payment', 'retry']
METRIC_KEYS = ['scheduled_retries', 'capped_retries', 'unsafe_retries', 'terminal_failures']
pr = select_incident_pr(REPO, ISSUE, TOPIC_TERMS)

artifact = json.loads(Path('/app/artifacts/payment_retry_replay.json').read_text())
api = os.environ.get('SLACK_API_URL', 'http://slack').rstrip('/') + '/api/conversations.history'
token = os.environ.get('SLACK_BOT_TOKEN', 'test-token-acme-eval')
data = urllib.parse.urlencode({'channel': 'incident-updates', 'limit': '50'}).encode()
req = urllib.request.Request(
    api,
    data=data,
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/x-www-form-urlencoded'},
    method='POST',
)
last = None
for _ in range(20):
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            obj = json.loads(response.read().decode())
        assert obj.get('ok'), obj
        # The handoff may be worded naturally. Check semantically stable facts over
        # the full channel history instead of literal phrases:
        texts = '\n'.join(m.get('text', '') for m in obj.get('messages', []))
        lowered = texts.lower()
        assert any_pr_reference([texts], pr, REPO), texts
        assert any(term in lowered for term in TOPIC_TERMS), texts
        assert re.search(r'\bartifact\b|\baudit\b|\breplay\b|/app/artifacts/', texts, re.I), texts
        for key in METRIC_KEYS:
            value = artifact[key]
            value_text = '/'.join(value) if isinstance(value, list) else str(value)
            humanized = key.replace('_', ' ')
            assert key in texts or humanized in lowered or value_text in texts, (key, texts)
        break
    except Exception as exc:
        last = exc
        time.sleep(0.5)
else:
    raise AssertionError(last)
print('slack handoff checks passed')
