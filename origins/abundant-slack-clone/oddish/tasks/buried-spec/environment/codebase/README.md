# acme-api

Rate-limiting service for the ACME API gateway.

## Setup
pip install pytest
python -m pytest

## Problem
The test suite is currently failing. The `ratelimit/bucket.py` constants are wrong —
they were updated after load testing but the repo was never patched. The agreed
production values are in the team's Slack workspace.
