#!/usr/bin/env python3
# Reproducibility: regenerate environment/data/overlay/. Run from the slack-clone checkout (SLACK_BASE).
# Plants a #engineering changelog message that references the real prod v8.5.0 build (#defect-and-
# blocker-thunderdome) plus a +9 delta; ts post-dates the prod corpus (ends 2025-12-19).
import sys, os
sys.path.insert(0, os.environ.get("SLACK_BASE","/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base"))
import slack_export_writer as sw
print(sw.write_export([{"channel":"engineering","author":"morgan.cole",
  "content":"Pulling together the hotfix changelog. The patched build number is 9 builds after whatever build v8.5.0 originally shipped as in #defect-and-blocker-thunderdome — can someone grab that original build number so I can finish the entry?",
  "timestamp":"2025-12-23T10:00:00Z"}], os.path.join(os.path.dirname(__file__),"overlay")))
