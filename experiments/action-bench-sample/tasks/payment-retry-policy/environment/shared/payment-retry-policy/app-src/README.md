# payment-retry-policy

Run `PYTHONPATH=/app/src python checks/visible_checks.py` from `/app/src`. The production context is in Linear and Slack.

The incident replay tool is `python tools/replay_payment_incident.py`. It writes `/app/artifacts/payment_retry_replay.json` for the Slack and ticket handoff.
