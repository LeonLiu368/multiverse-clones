The `checkout` service is failing some requests in production. Use the observability tooling to find
out **which API endpoint is returning HTTP 500 errors**, then write that endpoint's path to
`/workspace/answer.txt` (just the path, e.g. `/api/something/here`).

The logs are in Grafana/Loki — query them with the `gcx` CLI (it talks to the gauge service over
HTTP; `GRAFANA_URL` is already set):

```bash
gcx logs query '{service="checkout"}'                 # all checkout logs
gcx logs query '{service="checkout"} |= "500"'        # filter to the failing requests
```

The log data is only available through the tool — it is not on disk. Find the failing endpoint and
write its path to `/workspace/answer.txt`.
