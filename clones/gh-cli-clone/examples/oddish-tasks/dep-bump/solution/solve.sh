#!/usr/bin/env bash
set -euo pipefail
R=acme/api
cd /tmp && rm -rf api && gh repo clone acme/api && cd api
git checkout -b bump-requests
printf 'flask==2.0.1\nrequests==2.31.0\n' > requirements.txt
git add -A && git commit -m "security: bump requests to 2.31.0 (CVE-2023-32681)"
git push origin bump-requests
gh pr create -R $R -t "Bump requests to 2.31.0 (CVE-2023-32681)" -H bump-requests -B main -b "Fixes CVE-2023-32681"
gh issue create -R $R -t "Track CVE-2023-32681 (requests)" -b "Advisory CVE-2023-32681 affects requests < 2.31.0. PR opened to bump."
