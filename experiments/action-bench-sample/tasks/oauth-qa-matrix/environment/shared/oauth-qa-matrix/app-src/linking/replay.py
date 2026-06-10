import json
from pathlib import Path
from linking.coverage import coverage_summary, qa_matrix, required_flows

DEFAULT_ARTIFACT = Path("/app/artifacts/oauth_linking_qa.json")

def write_artifact(path=DEFAULT_ARTIFACT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = coverage_summary()
    payload["required_flows"] = required_flows()
    payload["matrix"] = qa_matrix()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload
