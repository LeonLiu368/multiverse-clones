from prometheus_operator.probe_policy import render_probe


distroless_local = {
    "instance_id": "probe-check-distroless",
    "image": "quay.io/prometheus/prometheus:v3.11.3-distroless",
    "image_flavor": "distroless",
    "listenLocal": True,
    "port": 9090,
}
shell_local = {
    "instance_id": "probe-check-shell",
    "image": "quay.io/prometheus/prometheus:v2.54.1",
    "image_flavor": "full",
    "listenLocal": True,
    "port": 9090,
}
distroless_public = {
    "instance_id": "probe-check-public",
    "image": "quay.io/prometheus/prometheus:v3.11.3-distroless",
    "image_flavor": "distroless",
    "listenLocal": False,
    "port": 9090,
}

probe = render_probe(distroless_local, "readiness")
assert "httpGet" in probe and "exec" not in probe, probe
assert probe["httpGet"]["path"] == "/-/ready", probe
assert probe["httpGet"]["port"] == 9090, probe
assert probe["httpGet"].get("host") == "127.0.0.1", probe

probe = render_probe(shell_local, "readiness")
assert "exec" in probe, probe
assert probe["exec"]["command"][0] == "sh", probe

probe = render_probe(distroless_public, "liveness")
assert "httpGet" in probe and "exec" not in probe, probe
assert probe["httpGet"]["path"] == "/-/healthy", probe
print("source behavior ok")
