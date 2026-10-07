# Data removed

This folder held `eng-prod-state.json`, the Jira "prod corpus": a real company's issue tracker export (8,040 issues, with personal contact details). It was removed from the public copy of this repository, including its history.

The `jira-gateway:prod-v1` image (`Dockerfile.gateway`) copies that file, so it won't build as-is. Build it from your own export with `tools/jira_to_state.py`, or use the empty gateway.
