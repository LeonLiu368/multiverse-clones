# Self-contained k3s server image for the conduit-live-k8s task.
#
# k3s runs its OWN embedded containerd (NO host docker.sock) in one privileged
# container — the self-contained deploy plane that works on Oddish/Daytona where
# the socket-sibling Dokku plane failed.
#
# Images are PULLED AT RUNTIME by k3s's containerd from PUBLIC registries. Every
# workload uses `imagePullPolicy: IfNotPresent`, so:
#   * on Oddish, k3s pulls the public ghcr/docker.io images at boot (no
#     --registry-login / docker-login needed — the two abundant-ai images are
#     published PUBLIC), and
#   * locally, images already imported into k3s's containerd are reused (see
#     validate_local.sh, which imports them so a run works before the public flip).
#
# (An earlier revision airgap-baked the images into the image; that produced a
# 422MB task upload that Oddish's S3 rejected — EntityTooLarge — so it is gone.)
#
# This image bakes ONLY the auto-applied manifests: k3s applies every manifest in
# /var/lib/rancher/k3s/server/manifests/*.yaml at boot — the whole stack (postgres,
# logfire, otel-collector, conduit SUT + seed Job) as k8s Deployments/Services.
# Path is relative to the compose build context (the `environment/` dir).
FROM rancher/k3s:v1.31.5-k3s1

COPY k3s/manifests/*.yaml /var/lib/rancher/k3s/server/manifests/
