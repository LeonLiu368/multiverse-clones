#!/usr/bin/env bash
set -euo pipefail
R=acme/inbox
gh label create -R $R -n bug -c d73a4a -d "real defect"
gh milestone create -R $R -t v1.1 -d "next release"
# #1 crash (keep), #2 security (keep), #3 dup of #1 (close), #4 cosmetic (leave)
gh issue edit 1 -R $R --add-label bug --milestone v1.1
gh issue edit 2 -R $R --add-label bug --milestone v1.1
gh issue comment 3 -R $R -b "Duplicate of #1."
gh issue close 3 -R $R
