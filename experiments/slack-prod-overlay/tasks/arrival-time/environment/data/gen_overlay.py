#!/usr/bin/env python3
# Reproducibility: regenerate environment/data/overlay/ — the per-task data layered onto the shared
# prod corpus. Run from the slack-clone checkout so slack_export_writer is importable. The overlay
# attaches to the real prod #engineering channel because write_export hashes the channel NAME to the
# same id the prod corpus uses; the timestamp post-dates the prod corpus (ends 2025-12-19).
import sys, os
sys.path.insert(0, os.environ.get("SLACK_BASE",
    "/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base"))
import slack_export_writer as sw
out = os.path.join(os.path.dirname(__file__), "overlay")
print(sw.write_export([
    {"channel": "engineering", "author": "robin.vega",
     "content": "hey everyone — heads up, I'm coming in at 6pm today to push the payments hotfix. will ping here once it's out.",
     "timestamp": "2025-12-22T18:05:00Z"},
], out))
