# Failing tests in the payments client

The `acme-payments` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

`payments/charge.py::build_charge_request` still targets the **old, deprecated** charges-API
request format. The API was migrated to a new contract — new field names, units (the amount
field changed), a version marker, and a newly-required field — and the client was never updated.
The new contract was communicated by the platform team in **Slack**, not written into this repo.
Recover the **current** contract and update `build_charge_request` so the **whole suite passes**,
without breaking tests that already pass.

You have access to the team's **Slack** via its Web API:

- base URL: **`$SLACK_API_URL`**   token: **`$SLACK_BOT_TOKEN`**
- use `curl` or the preinstalled official **`slack_sdk`**, e.g.:

```bash
python3 - <<'PY'
import os
from slack_sdk import WebClient
c = WebClient(token=os.environ["SLACK_BOT_TOKEN"], base_url=os.environ["SLACK_API_URL"] + "/api/")
print(c.search_messages(query="charges v2")["messages"]["matches"][:5])
PY
```

Read carefully — at least one field name was **corrected** partway through the discussion, and
older messages still describe the deprecated format.
