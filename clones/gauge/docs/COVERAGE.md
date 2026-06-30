# Gauge coverage matrix (R4)

Machine-checkable enumeration of the real Grafana **agent-used surface** that the gauge
clone emulates. Each row maps a capability to its HTTP endpoint, `gcx` CLI command,
`mcp-grafana` MCP tool, response-envelope fidelity, and whether it is **assessment-grade**
(see R5). Fidelity tier: **T2** (handwritten stdlib HTTP API + embedded PromQL/LogQL-style
query engine over JSON state).

Legend — **AG** = assessment-grade (≥3 of: stateful round-trip, multi-step, realistic
errors, query grammar, side-effecting devops shape). Envelope = Grafana-shaped response
(ids/prefixes/error codes/pagination match the product).

| # | Capability | HTTP endpoint | CLI (`gcx`) | MCP tool | Envelope | AG | Tested |
|---|---|---|---|---|---|---|---|
| 1 | Current user | `GET /api/user` | `whoami` | — (N/A: admin-ish, not in Grafana MCP) | ✅ | | ✅ |
| 2 | Org | `GET /api/org` | `whoami` (org field) | — (N/A) | ✅ | | ✅ |
| 3 | Dashboard search | `GET /api/search` | `dashboards search` | `search_dashboards` | ✅ | | ✅ |
| 4 | Dashboard get | `GET /api/dashboards/uid/{uid}` | `dashboards get` | `get_dashboard_by_uid` | ✅ | | ✅ |
| 5 | Dashboard summary | (derived from get) | `dashboards summary` | `get_dashboard_summary` | ✅ | | ✅ |
| 6 | Dashboard panel queries | (derived from get) | `dashboards panels` | `get_dashboard_panel_queries` | ✅ | | ✅ |
| 7 | Dashboard variables | (derived from get) | `dashboards variables` | `get_dashboard_variables` | ✅ | **AG** | ✅ |
| 8 | Dashboard property | (derived from get) | — (N/A: covered by summary/panels) | `get_dashboard_property` | ✅ | | ✅ |
| 9 | Panel query exec | `POST /api/ds/query` | `dashboards query-panel` | `run_dashboard_panel_query` | ✅ | **AG** | ✅ |
| 10 | Datasource list | `GET /api/datasources` | `datasources list` | `list_datasources` | ✅ | | ✅ |
| 11 | Datasource get | `GET /api/datasources/uid/{uid}` | `datasources get` | `get_datasource` | ✅ | | ✅ |
| 12 | Datasource health | (derived) | `datasources health` | — (N/A: derived from get) | ✅ | | ✅ |
| 13 | PromQL query | `POST /api/ds/query` | `metrics query` | `query_prometheus` | ✅ | **AG** | ✅ |
| 14 | Prom metric names | `POST /api/ds/query` | `metrics names` | `list_prometheus_metric_names` | ✅ | | ✅ |
| 15 | Prom label names | `POST /api/ds/query` | `metrics labels` | `list_prometheus_label_names` | ✅ | | ✅ |
| 16 | Prom label values | `POST /api/ds/query` | `metrics label-values` | `list_prometheus_label_values` | ✅ | **AG** | ✅ |
| 17 | LogQL query | `POST /api/ds/query` | `logs query` | `query_loki_logs` | ✅ | **AG** | ✅ |
| 18 | Loki label names | `POST /api/ds/query` | `logs labels` | `list_loki_label_names` | ✅ | | ✅ |
| 19 | Loki label values | `POST /api/ds/query` | `logs label-values` | `list_loki_label_values` | ✅ | | ✅ |
| 20 | Alert rules list | `GET /api/alert-rules` | `alert rules list` | `alerting_list_rules` | ✅ | **AG** | ✅ |
| 21 | Alert rule get | `GET /api/alert-rules/{uid}` | `alert rules get` | `alerting_get_rule` | ✅ | | ✅ |
| 22 | Alert instances | `GET /api/alert-instances` | `alert instances list` | `alerting_list_instances` | ✅ | **AG** | ✅ |
| 23 | Alert state history | `GET /api/alert-rules/{uid}/history` | `alert history` | `alerting_get_state_history` | ✅ | **AG** | ✅ |
| 24 | Annotations list | `GET /api/annotations` | `annotations list` | `get_annotations` | ✅ | | ✅ |
| 25 | **Annotation create** | `POST /api/annotations` | `annotations create` | `create_annotation` | ✅ | **AG (write→read RT)** | ✅ |
| 26 | Deeplinks | (computed) | `links dashboard/panel/explore` | `generate_deeplink` | ✅ | | ✅ |
| 27 | Query examples | (derived from dashboards) | — (N/A: MCP-only helper) | `get_query_examples` | ✅ | | ✅ |
| 28 | Health | `GET /api/healthz` | (config-check / health) | — (N/A: probe) | ✅ | | ✅ |

## Counts
- **28 capabilities** enumerated. **24 MCP tools**, **~24 CLI commands** (whoami/org/health
  are CLI-side; `get_dashboard_property`/`get_query_examples` are MCP-side helpers — each
  marked N/A on the other surface with a reason).
- **Parity** (R3.3): every dual-surface capability returns the same underlying data from the
  CLI and the MCP tool — proven in-process by `tests/test_parity.py` (CLI `--json` ==
  matching MCP tool output, byte-equal after key-sorting).
- **Assessment-grade (R5):** **8** rows flagged **AG** (≥5 required): PromQL query (13),
  LogQL query (17), Prom/Loki label-values multi-step (16), dashboard variables (7), panel
  query exec (9), alert rules list+filter (20), alert instances list+filter (22), alert
  state-history devops shape (23), and **annotation create** (25) — the write→read
  round-trip exercised end-to-end by `tests/test_api_annotations.py`,
  `tests/test_parity.py::test_parity_write_read_roundtrip`, and the bundled Harbor task
  `oddish/tasks/gauge-annotation-roundtrip`.

## Operator-only (never on the agent surface)
| Capability | HTTP endpoint | Admin CLI | Why operator-only |
|---|---|---|---|
| Clone state snapshot | `GET /api/_clone/state` (admin token) | `gaugectl state` | World inspection; gateway-only, stripped from the agent |
| Mutation log | `GET /api/_clone/mutations` (admin token) | `gaugectl mutations` | Verifier/operator audit of agent writes; not an agent tool |

## Error envelopes (R4.3 / R5 realistic errors)
- Unknown uid → `404 {"message":"Not found"}`; CLI exits `2` (`NotFoundError`), MCP →
  `isError`. Missing/invalid token → `401`/`403`; CLI exits `3`. Unknown MCP tool / bad args
  → JSON-RPC `-32602`. Internal failure → `500 {"message":"Gauge internal error: ..."}`;
  CLI exits `5`. Covered by `tests/test_cli_gcx.py`, `tests/test_mcp_grafana.py`,
  `tests/test_api_*`.
