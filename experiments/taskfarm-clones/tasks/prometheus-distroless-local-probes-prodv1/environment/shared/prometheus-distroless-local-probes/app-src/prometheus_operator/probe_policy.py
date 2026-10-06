ENDPOINTS = {
    "liveness": "/-/healthy",
    "readiness": "/-/ready",
    "startup": "/-/ready",
}


def is_distroless(instance):
    image = str(instance.get("image", "")).lower()
    flavor = str(instance.get("image_flavor", "")).lower()
    return "distroless" in image or flavor == "distroless"


def render_probe(instance, probe_type):
    """Render a Kubernetes probe for one Prometheus instance.

    Bug: listenLocal probes always use a shell/curl exec path, even when the
    target Prometheus image is distroless and has no shell.
    """
    path = ENDPOINTS.get(probe_type, "/-/ready")
    port = int(instance.get("port", 9090))
    if bool(instance.get("listenLocal")):
        command = (
            f'if [ -x "$(command -v curl)" ]; then exec curl --fail http://localhost:{port}{path}; '
            f'elif [ -x "$(command -v wget)" ]; then exec wget -q -O /dev/null http://localhost:{port}{path}; '
            "else exit 1; fi"
        )
        return {
            "exec": {"command": ["sh", "-c", command]},
            "periodSeconds": 5,
            "timeoutSeconds": 3,
        }
    return {
        "httpGet": {"path": path, "port": port, "scheme": "HTTP"},
        "periodSeconds": 5,
        "timeoutSeconds": 3,
    }
