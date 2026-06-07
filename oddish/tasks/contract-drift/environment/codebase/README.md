# acme-analytics

Analytics event publisher for the ACME platform.

## Setup
pip install pytest
python -m pytest

## Problem
The analytics pipeline migrated to schema v2. The `events/publisher.py` function still
produces v1 payloads. The v2 field names and format requirements were announced in the
team's Slack workspace.
