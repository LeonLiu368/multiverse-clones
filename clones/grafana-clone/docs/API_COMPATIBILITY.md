# API Compatibility

Grafana implements a practical Grafana-compatible subset for benchmark tasks. Unsupported areas return clear errors or empty results rather than pretending to be full Grafana.

## HTTP API

| Grafana endpoint | Grafana concept | Support |
| --- | --- | --- |
| `GET /api/healthz` | service health | Grafana-specific health |
| `GET /api/user` | current user | supported subset |
| `GET /api/org` | current org | supported subset |
| `GET /api/search?query=&type=dash-db` | dashboard search | dashboard search only |
| `GET /api/dashboards/uid/{uid}` | dashboard by uid | supported subset |
| `GET /api/datasources` | datasource list | supported subset |
| `GET /api/datasources/uid/{uid}` | datasource by uid | supported subset |
| `POST /api/ds/query` | datasource query | embedded Prometheus/Loki subset |
| `GET /api/alert-rules` | alerting rules | supported subset |
| `GET /api/alert-rules/{uid}` | alerting rule | supported subset |
| `GET /api/alert-instances` | alert instances | Grafana-compatible subset |
| `GET /api/alert-rules/{uid}/history` | alert state history | Grafana-compatible subset |
| `GET /api/annotations` | annotation search | supported subset |
| `POST /api/annotations` | annotation create | supported subset |

Grafana also exposes verifier/admin endpoints at `/api/_clone/state` and `/api/_clone/mutations`. They are not agent tools, require `GRAFANA_ENABLE_ADMIN_API=1`, and require `GRAFANA_ADMIN_TOKEN`; normal Grafana tokens receive `403`.

## Tool Mapping

`gcx` and `mcp-grafana` mirror the real Grafana ecosystem enough for incident workflows:

- dashboard discovery and inspection
- datasource discovery
- Prometheus-style queries and label discovery
- Loki-style log queries and label discovery
- alert rule inspection
- alert instance and state history inspection
- annotations
- dashboard, panel, and Explore deeplinks
- dashboard variables and panel-query execution

Unsupported in v1:

- full PromQL evaluation
- full LogQL evaluation
- dashboard editing
- alert rule editing
- external Prometheus/Loki/Tempo delegation
- Grafana Cloud APIs
- real identity, teams, folders, permissions, or plugins
