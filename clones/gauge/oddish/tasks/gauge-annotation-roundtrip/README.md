# gauge-annotation-roundtrip

Harbor/Oddish observability tool-use task on the **gauge** clone (Grafana-compatible).

A payment-webhook alert is **firing**. The agent must use the gauge tools (`gcx` CLI +
`mcp-grafana` MCP server) to find the firing alert's rule uid, recover the root-cause
keyword (`lock_conflict`) from the Loki logs, and post a Grafana **annotation** on
`dash-payment-webhooks` panel 1 that references both, tagged `incident`. The verifier
reads the annotation back through the API (write→read round-trip) — narration is not
trusted, and the seed corpus ships zero annotations so a nop run scores 0.

## Shape
- **`main`** (agent) — thin gauge-agent: `gcx` + `mcp-grafana` only, no data, no server
  source (`import gauge.server.state` raises). Built by Harbor from `environment/Dockerfile`.
- **`gauge`** (gateway) — the clone HTTP API; `build:`+`image:` dual so it builds locally
  and never needs a GHCR pull. Corpus delivered by mounting `fixture.json` into the gateway
  ONLY. (A prod variant would use `gauge-service:prod-v1` with the corpus baked in, no mount.)

## Verify locally
```bash
bash validate_local.sh        # builds both images, checks nop=0 / oracle=1 / decoy=0 + isolation
```

`tests/test.sh` writes `/logs/verifier/reward.txt`; `solution/solve.sh` is the oracle.
