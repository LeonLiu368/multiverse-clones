# k3s self-contained spike — PASSED (cloud deploy-plane pivot from Dokku)

Why: the Dokku deploy plane is **socket-sibling** (mounts the sandbox `/var/run/docker.sock`,
spawns sibling containers on the shared daemon). On Oddish this broke Harbor's own DinD-compose
file-transfer to `main` (`harbor/environments/dind_compose.py::_fetch_file_from_host`), and some
Daytona sandboxes couldn't start a nested dockerd at all (`/sys/fs/cgroup: read-only`). k3s runs
its **own embedded containerd in one privileged container — no host docker.sock** — the same
self-contained approach that lets retry-storm run k8s on Daytona.

Proven (local Docker Desktop arm64), all in `docker-compose.yaml`:
| Check | Result |
|---|---|
| k3s boots (privileged, `--snapshotter native`, no docker.sock) | **healthy in 32s** |
| `/var/run/docker.sock` in the k3s container | **absent** (own containerd) |
| compose sibling → cluster via kubeconfig (server rewritten `127.0.0.1`→`k3s:6443`) | node Ready |
| apply Deployment + Service | ok |
| **agent remediation: `kubectl set env deploy/x KEY=V` → rollout** | **1s** (vs Dokku 30s) |
| compose sibling → in-cluster svc via NodePort (`http://k3s:30080`) | reachable |

Implication for the task re-platform: only **2 compose services** (`k3s` privileged + `main`);
the whole stack (postgres, logfire, otel-collector, SUT) runs as k8s manifests INSIDE k3s
(drop into `/var/lib/rancher/k3s/server/manifests/` for auto-apply at boot). Agent reaches
logfire via a NodePort; remediates via `kubectl set env deploy/conduit WEB_CONCURRENCY=4`.
Images should be PUBLIC on ghcr (k3s containerd pulls public images without the docker-login
that `--registry-login` provides), or baked/imported — avoids the containerd registry-auth wrinkle.
