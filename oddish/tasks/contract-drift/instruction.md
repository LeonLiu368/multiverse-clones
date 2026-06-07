# Analytics pipeline schema drift

The `acme-analytics` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`events/publisher.py::build_event_payload` returns a v1-format payload — the analytics
pipeline was migrated to **schema v2**, but the function was never updated. The v2 field
names, types, and format requirements were announced by the data platform team in the team's
Slack workspace. They are **not** recorded in this repo.

Recover the v2 spec and update `build_event_payload` so the full suite passes without
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

Read carefully — there was a mid-thread correction on one of the field names; use the
corrected name, not the original suggestion.
