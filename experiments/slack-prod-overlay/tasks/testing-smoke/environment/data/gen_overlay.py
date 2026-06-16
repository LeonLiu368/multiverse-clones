#!/usr/bin/env python3
# Reproducibility: regenerate environment/data/overlay/ — one extra "testing" message planted in the
# WorldsDataTest workspace. Run from the slack-clone checkout (SLACK_BASE). ts post-dates the corpus.
import sys, os
sys.path.insert(0, os.environ.get("SLACK_BASE","/Users/leonliu/projects/abundant-slack-clone-mattermost/selfcontained/base"))
import slack_export_writer as sw
print(sw.write_export([{"channel":"all-worldsdatatest","author":"dana.reed",
  "content":"just finished testing the latest build, looks good to ship","timestamp":"2026-06-12T09:00:00Z"}],
  os.path.join(os.path.dirname(__file__),"overlay")))
