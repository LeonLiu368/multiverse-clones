#!/bin/sh
# k3s launcher. Tries to PIN the node IP to this container's compose-network
# address so the apiserver + NodePorts bind where the `main` agent can route
# (on multi-homed Daytona, k3s otherwise auto-picks the host public IP, which is
# unreachable from `main`). But NEVER regress boot: if we can't determine a sane
# container IP, omit --node-ip and let k3s auto-detect (which at least starts).
#
# Also TEE k3s's own stdout/stderr to the shared `kube` volume (/output/k3s-boot.log)
# so that when k3s crashes at boot on a given Daytona host, `main` can surface the
# crash reason (Harbor never captures a dead sibling's container logs — only compose
# orchestration lines — so without this the failure is invisible/undebuggable).
set -e

# Prefer the source IP k3s's own outbound traffic would use (its real interface),
# then fall back to the first hostname address. Validate it's a plausible IPv4 and
# actually configured on a local interface before trusting it.
pick_ip() {
  for cand in \
    "$(getent hosts "$(hostname)" 2>/dev/null | awk '{print $1; exit}')" \
    $(hostname -i 2>/dev/null) \
    "$(hostname -I 2>/dev/null | awk '{print $1}')"
  do
    case "$cand" in
      ""|127.*|169.254.*|*:*) continue ;;            # empty / loopback / link-local / IPv6
      *.*.*.*) printf '%s\n' "$cand"; return 0 ;;
    esac
  done
  return 0
}

IP="$(pick_ip)"
FLAGS="--disable traefik --disable metrics-server --snapshotter native --tls-san k3s"
if [ -n "$IP" ]; then
  echo "[k3s-entrypoint] pinning node-ip=$IP"
  FLAGS="$FLAGS --node-ip $IP --advertise-address $IP"
else
  echo "[k3s-entrypoint] no reliable container IP; letting k3s auto-detect (boot-safe)"
fi

# Boot log lands on the shared volume (main mounts it read-only at /mnt/kube).
# CRUCIAL: keep `exec` so k3s stays the foreground/PID-1 process — it manages
# containerd + kubelet as children and CRASHES if merely backgrounded under a
# shell. We only redirect k3s's own fd 1/2 to the volume file; that changes where
# its logs land, not how it runs. main reads $LOG to surface any boot crash.
LOG=/output/k3s-boot.log
mkdir -p /output
echo "[k3s-entrypoint] launching k3s (boot log -> $LOG); flags:$FLAGS"
# shellcheck disable=SC2086
exec /bin/k3s server $FLAGS "$@" > "$LOG" 2>&1
