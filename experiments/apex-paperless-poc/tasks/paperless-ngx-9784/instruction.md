## Your Task

I'm working on a document management system that handles a lot of read-heavy traffic, and I need to add an optional caching layer to reduce database load. Right now, every query hits the database directly, which works fine for smaller installations but becomes a bottleneck for larger deployments with thousands of documents. I'd like administrators to be able to opt into Redis-based query caching through configuration, with the ability to set how long cached results stay valid before refreshing from the database. The caching should be completely disabled by default so existing installations aren't affected, and when it is enabled, admins should have a way to manually flush the cache when they need fresh data immediately.

## Available Tools
This is an observability task — use the observability + collaboration tools. The repo is at `/app/repo`.
- Logs (Grafana/Loki): `gcx logs query '{{service="paperless-ngx"}}'` (filter with `|= "500"` etc.), `gcx dashboards list`
- Issue tracker: `linear issue list`, `linear issue search "<term>"` (or the `jira` CLI)
- Team chat: `slack channels list`, `slack messages search "<term>"`
Correlate these, then fix the root cause in `/app/repo`. Do not modify the test suite.
