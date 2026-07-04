# Self-contained k3s server image for the conduit-live-k8s task.
#
# k3s runs its OWN embedded containerd (NO host docker.sock) in one privileged
# container — the self-contained deploy plane that works on Oddish/Daytona where
# the socket-sibling Dokku plane failed.
#
# This image bakes TWO things at build time so the cluster is hermetic at boot:
#
#  1. AIRGAP IMAGES  -> /var/lib/rancher/k3s/agent/images/*.tar
#     k3s auto-imports every tar here into its containerd at startup, so the
#     workloads never pull from a registry. This sidesteps the one k3s wrinkle:
#     k3s uses containerd, not docker, so Oddish's `--registry-login` (a
#     `docker login`) does NOT authenticate k3s image pulls. Baking avoids all
#     runtime registry auth — public AND private images alike.
#     The tars are produced on the host by ./bake-images.sh (docker save of
#     postgres:16, otel-collector, the private logfire-service, and the locally
#     built conduit-otel SUT) into ./airgap/ before this build.
#
#  2. AUTO-APPLIED MANIFESTS -> /var/lib/rancher/k3s/server/manifests/*.yaml
#     k3s applies every manifest dropped here at boot: the whole stack (postgres,
#     logfire, otel-collector, conduit SUT + seed Job) as k8s Deployments/Services.
FROM rancher/k3s:v1.31.5-k3s1

# Paths are relative to the compose build context (the `environment/` dir).
#
# 1. airgap image tars (imported into containerd at boot; imagePullPolicy: Never
#    on every workload, so no registry is ever contacted)
COPY k3s/airgap/*.tar /var/lib/rancher/k3s/agent/images/

# 2. stack manifests (auto-applied at boot, in filename order)
COPY k3s/manifests/*.yaml /var/lib/rancher/k3s/server/manifests/
