Run `PYTHONPATH=/app/src python checks/visible_checks.py` from `/app/src`. The OAuth QA artifact tool is `python tools/replay_oauth_qa.py`.

Use the canonical flow identifier `oauth_app_to_app_chase_device` for the Chase app-to-app device validation row. Mark that row with `requires_device=True`; do not shorten it to `oauth_app_to_app_chase` or extend it with `_validation`.
