# On-call: document the payment-webhook incident in Grafana

You are on call for the **payments** service. A Grafana alert is **firing** and the
payment-webhook dashboard is lit up. Your job is to investigate using the Grafana tools
(`gcx` CLI and the `grafana`/`mcp-grafana` MCP server, both pointed at the `grafana` service)
and then record what you found as a Grafana **annotation** on the dashboard panel, so the
next responder has the context.

Concretely, you must:

1. Find the alert instance that is currently in the **firing** state and note its rule uid.
2. Query the Loki logs for the payments service to find the **root-cause keyword** in the
   warning log line (it is the specific failure mode the gateway is hitting).
3. Create an annotation on dashboard **`dash-payment-webhooks`**, panel **`1`**, whose text:
   - references the firing alert's rule **uid**, and
   - names the **root-cause keyword** you found in the logs,
   and is tagged **`incident`**.

You only have the Grafana tools — there is no local copy of the dashboards, logs, or
alerts. Discover everything through the API. The annotation is read back through the
Grafana API to grade your work, so it must actually exist on the server (narration is not
enough).

Tools available: `gcx` (CLI) and the `grafana` MCP server (`mcp-grafana`). Useful starting
points: `gcx alert instances list --state firing`, `gcx logs query`, `gcx annotations create`.
