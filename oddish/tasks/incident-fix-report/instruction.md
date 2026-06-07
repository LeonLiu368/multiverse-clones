# Error-budget monitor: wrong alert thresholds

The `acme-sre-tools` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`budget/monitor.py::check_budget` has **wrong alert thresholds and paging conditions** — they
were set to placeholder values and revised in an SLO review, but the repo was never updated.
The agreed thresholds live in the team's Slack workspace.

Once you fix the code so the suite passes, also **post a notification** to Slack channel
`#error-budget-reports` confirming the thresholds you applied. The notification must include
the `error_rate` threshold and the `budget` threshold values.

You have access to the team's **Slack** via its Web API:

- base URL: **`$SLACK_API_URL`**  token: **`$SLACK_BOT_TOKEN`**
- use `curl` or the preinstalled official **`slack_sdk`**:

```bash
python3 - <<'PY'
import os
from slack_sdk import WebClient
c = WebClient(token=os.environ["SLACK_BOT_TOKEN"], base_url=os.environ["SLACK_API_URL"] + "/api/")
print([ch["name"] for ch in c.conversations_list()["channels"]])
PY
```

Several thresholds were proposed and revised during the SLO review — use the **final agreed
values**, not earlier proposals. The paging condition also involves latency.
