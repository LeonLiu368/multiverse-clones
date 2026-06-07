# Pager-fatigue incident: fix the alert and write the postmortem

The `acme-monitoring` codebase is checked out at **`/workspace`**. Its test suite is failing:

```bash
cd /workspace && python -m pytest -q
```

On-call has been paged at 3am all week. `monitoring/alerts.py::should_page` is unimplemented
after the team agreed a new paging policy **during the incident** — but that policy was never
written into the repo. Two things to do:

1. **Fix the code.** Recover the agreed paging policy and implement `should_page` so the whole
   suite passes (don't break tests that already pass).
2. **Write the postmortem.** Post a short postmortem to the **#postmortems** Slack channel that
   states the **root cause** of the pager fatigue and the agreed fix.

You have access to the team's **Slack** via its Web API:

- base URL: **`$SLACK_API_URL`**   token: **`$SLACK_BOT_TOKEN`**
- use `curl` or the preinstalled official **`slack_sdk`** (read `#incidents`; post to
  `#postmortems` with `chat.postMessage`), e.g.:

```bash
python3 - <<'PY'
import os
from slack_sdk import WebClient
c = WebClient(token=os.environ["SLACK_BOT_TOKEN"], base_url=os.environ["SLACK_API_URL"] + "/api/")
c.chat_postMessage(channel="postmortems", text="ROOT CAUSE: ...")
PY
```

Read carefully — there is a red herring in the discussion, and the *old* alert thresholds still
appear in older messages.
