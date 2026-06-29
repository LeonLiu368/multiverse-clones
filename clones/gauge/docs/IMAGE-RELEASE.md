# Image Release

Gauge publishes one reusable service image:

```text
ghcr.io/abundant-ai/gauge-service:main
```

The image contains:

- the Gauge HTTP service on port 80
- `/usr/local/bin/gcx`
- `/usr/local/bin/mcp-grafana`
- `/usr/local/bin/gaugectl`
- `/opt/gaugecli`

`/opt/gaugecli` is compatible with Python 3.10+ agent images.
The admin API is disabled by default in the image; examples enable it with `GAUGE_ENABLE_ADMIN_API=1` and a test-only `GAUGE_ADMIN_TOKEN`.

## Local Build

```bash
docker build -f Dockerfile.service -t gauge-service:local .
docker compose -f examples/docker-compose.yaml up -d
curl -sf http://localhost:3000/api/healthz
GRAFANA_URL=http://localhost:3000 GAUGE_ADMIN_TOKEN=test-admin-token-acme-eval bin/gaugectl mutations
docker compose -f examples/docker-compose.yaml down -v
```

## CI

`.github/workflows/build-service-image.yml` runs tests, builds the image, runs the example Compose smoke test, and pushes to GHCR on `main`.

Task packs should pin by digest:

```text
ghcr.io/abundant-ai/gauge-service:main@sha256:<digest>
```
