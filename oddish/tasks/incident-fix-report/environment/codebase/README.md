# acme-sre-tools

SRE tooling for the ACME platform: error-budget monitoring and alerting.

## Setup
pip install pytest
python -m pytest

## Problem
The test suite is failing. `budget/monitor.py::check_budget` has wrong alert thresholds.
The agreed thresholds and paging conditions were decided in an SLO review in the team's
Slack workspace. Additionally, once you fix the code, post a notification to Slack
(channel: #error-budget-reports) reporting the thresholds you applied.
