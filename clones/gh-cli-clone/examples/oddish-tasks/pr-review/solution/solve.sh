#!/usr/bin/env bash
set -euo pipefail
R=acme/lib
gh pr list -R $R
cd /tmp && rm -rf lib && gh repo clone acme/lib && cd lib
gh pr checkout 1 -R $R
gh pr diff 1 -R $R
gh pr close 1 -R $R
gh pr reopen 1 -R $R
