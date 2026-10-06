#!/bin/bash
# Oracle solution: query the Tasks DB for the target page, mark it Done, post the
# confirmation comment. Uses only the agent tools (notion-cli) over the API.
set -euo pipefail
export NOTION_API_URL="${NOTION_API_URL:-http://notion:3000}"

# 1. locate the Tasks database id
DBID=$(notion-cli search "Tasks" --type database | python3 -c '
import json,sys
d=json.load(sys.stdin)
for r in d["results"]:
    if "".join(t["plain_text"] for t in r.get("title",[]))=="Tasks":
        print(r["id"]); break
')

# 2. find the target page id by querying the database
PID=$(notion-cli databases query "$DBID" \
        --filter "{\"property\":\"Name\",\"title\":{\"equals\":\"Rotate prod database creds\"}}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])')

# 3. mark Status=Done and Done=true
notion-cli pages update "$PID" --properties \
  '{"Status":{"type":"status","status":{"name":"Done"}},"Done":{"type":"checkbox","checkbox":true}}' >/dev/null

# 4. post the confirmation comment
notion-cli comments add "$PID" -m "Production database credentials have been rotated." >/dev/null

echo "oracle: marked '$PID' Done and posted the rotation comment"
