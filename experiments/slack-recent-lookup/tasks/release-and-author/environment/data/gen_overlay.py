#!/usr/bin/env python3
# Reproducibility: regenerate environment/data/overlay/. Run from the slack-clone checkout (SLACK_BASE).
# Plants ONE recent note in the real prod #release-status channel, dated just after the corpus tail
# (2025-12-19), so it reads as "the most recent activity".
import sys, os
sys.path.insert(0, os.environ.get("SLACK_BASE","/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base"))
import slack_export_writer as sw
print(sw.write_export([{"channel":"release-status","author":"dana.reed",
  "content":"Scheduling note: the v9.0.0 release is set to go live on December 22. Please lock your changes by EOD Friday.",
  "timestamp":"2025-12-20T16:30:00Z"}], os.path.join(os.path.dirname(__file__),"overlay")))
