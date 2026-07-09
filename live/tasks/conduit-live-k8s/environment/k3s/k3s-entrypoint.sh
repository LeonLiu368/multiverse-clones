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

# cgroup v2 nesting fix (the standard k3s-in-docker/k3d dance): on cgroup v2,
# the container's ROOT cgroup holds our processes, and the "no internal process"
# rule then forbids creating child cgroups with controllers — which is exactly
# what kubelet/containerd must do, so k3s dies at boot on hosts whose nested
# dockerd doesn't pre-delegate. Evacuate PIDs to /init and enable subtree
# control. Every write is || true: on hosts that don't need it (or where cgroupfs
# is read-only) this is a no-op, never a new failure mode.
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  echo "[k3s-entrypoint] cgroup v2 detected; enabling nested delegation"
  mkdir -p /sys/fs/cgroup/init 2>/dev/null || true
  # busybox xargs supports -r and -n1
  xargs -rn1 < /sys/fs/cgroup/cgroup.procs > /sys/fs/cgroup/init/cgroup.procs 2>/dev/null || true
  sed -e 's/ / +/g' -e 's/^/+/' < /sys/fs/cgroup/cgroup.controllers \
    > /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null || true
fi

IP="$(pick_ip)"
# host-gw flannel backend: vxlan (the default) needs the vxlan kernel module,
# which nested/Daytona sandboxes may lack -> every pod stuck ContainerCreating
# while the control plane looks healthy. host-gw just programs routes; on a
# single-node cluster it is equivalent and dependency-free.
FLAGS="--disable traefik --disable metrics-server --snapshotter native --tls-san k3s --flannel-backend=host-gw"
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
