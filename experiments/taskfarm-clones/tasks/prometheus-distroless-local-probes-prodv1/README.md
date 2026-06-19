# Prometheus Distroless Local Probes

This Harbor task is a scoped Kubernetes/operator incident derived from Prometheus Operator issue 8605. It includes a small operator-style repo, Postgres incident state, TicketVector handoff data, k3s evidence objects, and Grafana context.

Primary workflow:

- inspect `/app/src/prometheus_operator/probe_policy.py` and `ops/prometheus_instances.yaml`
- use Postgres, k3s, GitHub, and Grafana evidence to confirm scope
- patch the renderer
- run `python3 tools/build_distroless_probe_repair.py --apply`
- update `PROMOP-8605` in TicketVector

The deliverable starts unsolved. The verifier expects the final artifact and handoff state to be produced by the agent.
