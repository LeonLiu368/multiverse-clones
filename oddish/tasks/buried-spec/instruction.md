# Failing tests in the billing service

The `acme-billing` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`billing/fees.py::overdue_fee` was never implemented. The team **agreed the exact policy**
(grace period, tier rates, minimum, cap, rounding, edge cases) in their Slack workspace — it is
not written into the repo. Recover it and implement `overdue_fee` so the **whole suite passes**,
without breaking tests that already pass.

You have access to the team's **Slack** via its Web API:

- base URL: **`$SLACK_API_URL`**   token: **`$SLACK_BOT_TOKEN`**
- use `curl` or the preinstalled official **`slack_sdk`**, e.g.:

```bash
python3 - <<'PY'
import os
from slack_sdk import WebClient
c = WebClient(token=os.environ["SLACK_BOT_TOKEN"], base_url=os.environ["SLACK_API_URL"] + "/api/")
print([ch["name"] for ch in c.conversations_list()["channels"]])
PY
```

Read carefully — several **earlier proposals were revised** before the team settled, so use the
*agreed* values, not superseded ones.
