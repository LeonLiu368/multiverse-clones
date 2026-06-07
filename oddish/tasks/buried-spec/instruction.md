# Rate limiter misconfiguration

The `acme-api` codebase is checked out at **`/workspace`**. Its test suite is currently failing:

```bash
cd /workspace && python -m pytest -q
```

`ratelimit/bucket.py` defines four configuration constants — `CAPACITY`, `REFILL_RATE`,
`INITIAL_TOKENS`, and `OVERDRAFT_ALLOWANCE` — that are **wrong**. They were set to conservative
placeholder values during initial development and revised after a load-testing exercise, but the
repo was never updated. The agreed production values live only in the team's Slack workspace.

Recover the agreed values and update the constants so the full test suite passes without
breaking tests that already pass.

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

Several values were proposed and revised during the load-test discussion — use the **final
agreed values**, not superseded proposals.
