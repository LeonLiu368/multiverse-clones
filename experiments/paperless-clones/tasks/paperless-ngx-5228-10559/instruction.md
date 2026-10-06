## Your Task

I'm organizing documents with filepath templates in Paperless NGX and I need a way to localize dates right inside the templating engine. So, right now the formatting follows a single process locale, so I can't switch languages per template or per path, and I can't reliably produce locale specific strings on demand. I'd love a new filter that takes a date or datetime and returns a string formatted using an explicit locale and a format pattern, so I can, for example, keep most of a path in English but render a month name in German for a subfolder. It should not mutate global or process locale, should be thread safe, and should leave existing templates unchanged when the filter is not used. It needs to accept both naive and timezone aware datetimes, provide a sensible default when no format is supplied, and fail clearly for unsupported or missing locales with a readable error or documented fallback. I also want to make sure about the consistent behavior across platforms and filename safe output with no surprises.

## Available Tools
This is an observability task — use the observability + collaboration tools. The repo is at `/app/repo`.
- Logs (Grafana/Loki): `gcx logs query '{service="paperless-ngx"}'` (filter with `|= "500"` etc.), `gcx dashboards list`
- Issue tracker: `linear issue list`, `linear issue search "<term>"` (or the `jira` CLI)
- Team chat: `slack channels list`, `slack messages search "<term>"`
Correlate these, then fix the root cause in `/app/repo`. Do not modify the test suite.
