#!/bin/bash
# Deterministic verifier: reads task state back THROUGH the Notion API (never off
# disk) and writes a reward in [0,1] to /logs/verifier/reward.txt.
#
# Grades the write->read round-trip:
#   * the "Rotate prod database creds" task page has Status == Done
#   * its Done checkbox == true
#   * a comment on that page contains the word "rotated"
# All three required for full reward (1.0); 0.0 otherwise.
set -uo pipefail
REWARD_DIR="${REWARD_DIR:-/logs/verifier}"
mkdir -p "$REWARD_DIR"
export REWARD_DIR

python3 - <<'PY'
import os, sys
from notionclone.client import NotionClient, NotionAPIError

REWARD = os.path.join(os.environ.get("REWARD_DIR", "/logs/verifier"), "reward.txt")

def fail(msg, score=0.0):
    print("VERIFY:", msg)
    open(REWARD, "w").write(str(score))
    sys.exit(0)

c = NotionClient()

# 1. find the Tasks database
try:
    dbs = c.search("Tasks", object_type="database")["results"]
except NotionAPIError as e:
    fail(f"search failed: {e}")
db = next((d for d in dbs if "".join(t["plain_text"] for t in d.get("title", [])) == "Tasks"), None)
if not db:
    fail("Tasks database not found")

# 2. find the target page by querying the database
res = c.query_database(db["id"], filter_obj={"property": "Name", "title": {"equals": "Rotate prod database creds"}})
pages = res["results"]
if not pages:
    fail("target task page not found")
page = pages[0]
props = page["properties"]

status = (props.get("Status", {}).get("status") or {}).get("name")
done = props.get("Done", {}).get("checkbox")
if status != "Done":
    fail(f"Status is {status!r}, expected 'Done'")
if done is not True:
    fail(f"Done checkbox is {done!r}, expected True")

# 3. confirmation comment containing 'rotated'
comments = c.list_comments(page["id"])["results"]
texts = [" ".join(t["plain_text"] for t in cm.get("rich_text", [])).lower() for cm in comments]
if not any("rotated" in t for t in texts):
    fail("no comment containing 'rotated' on the task page")

print("VERIFY: all checks passed")
open(REWARD, "w").write("1.0")
PY
