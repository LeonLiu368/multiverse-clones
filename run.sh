#!/usr/bin/env bash
# Boot the seed-dashboard for local dev: FastAPI backend on :8000 + Vite frontend on :5273.
# The frontend proxies /api -> :8000, so just open http://localhost:5273.
#
#   ./run.sh
#   SLACK_CLONE_BASE=/path/to/abundant-slack-clone-mattermost/selfcontained/base ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

export SLACK_CLONE_BASE="${SLACK_CLONE_BASE:-/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base}"

# backend
cd backend
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
( uvicorn app:app --port 8000 --reload ) &
BACK=$!
cd ..

# frontend
cd frontend
[ -d node_modules ] || npm install
( npm run dev ) &
FRONT=$!
cd ..

echo "backend pid=$BACK  frontend pid=$FRONT"
echo "open http://localhost:5273"
trap 'kill $BACK $FRONT 2>/dev/null || true' INT TERM
wait
