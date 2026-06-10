import json
from pathlib import Path
p=Path('/app/artifacts/oauth_linking_qa.json')
assert p.exists(), 'missing oauth QA artifact'
data=json.loads(p.read_text())
assert data['total_flows'] == 10, data
assert data['missing_flows'] == [], data
assert data['update_mode_flows'] == 3, data
assert data['device_required_flows'] == ['oauth_app_to_app_chase_device'], data
assert len(data['matrix']) == 10, data
print('oauth artifact checks passed')
