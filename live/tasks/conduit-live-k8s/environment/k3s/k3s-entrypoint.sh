#!/bin/sh
# k3s launcher that PINS the node IP to this container's compose-network address.
#
# Why: on multi-homed Daytona sandboxes, k3s auto-detects the *host's* public IP
# (e.g. 3.230.196.84) as its node IP, then advertises it in the kubeconfig AND
# binds NodePorts there — unreachable from the `main` agent, which reaches this
# container by the compose service name `k3s`. Both symptoms → `main` can't hit
# the apiserver (6443) or the logfire/SUT NodePorts → the soak infra_errors.
# Locally (single-homed) k3s picks the container IP correctly, so it only bit on
# Oddish. Forcing --node-ip/--advertise-address to `hostname -i` makes the
# apiserver + kube-proxy bind on the interface `main` actually routes to.
set -e
IP="$(hostname -i 2>/dev/null | awk '{print $1}')"
echo "[k3s-entrypoint] pinning node-ip=$IP (was auto-detected before)"
exec /bin/k3s server \
  --disable traefik \
  --disable metrics-server \
  --snapshotter native \
  --tls-san k3s \
  --node-ip "$IP" \
  --advertise-address "$IP" \
  "$@"
