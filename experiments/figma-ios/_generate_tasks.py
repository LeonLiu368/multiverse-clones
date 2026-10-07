#!/usr/bin/env python3
"""Generate a batch of Figma 'list-the-variants' tasks from the real iOS corpus.

Each spec targets a unique COMPONENT_SET in the baked prod-v1 corpus. For every
task we emit: a trimmed :empty fixture (just that set's subtree), a codebase stub,
visible + hidden tests, an oracle, and the thin-agent / variant-switch wiring.
Same file key across all tasks, so each runs on :empty (mounted slice) OR :prod-v1
(baked full corpus) by the FIGMA_SERVICE_IMAGE switch.
"""
import json, os, subprocess, sys, stat, textwrap

KEY = "R1jno9FuCgYkNXayz8zglW"
FULL = json.load(open("/tmp/ios_full.json"))
FIGMA_CLI = os.environ.get("FIGMA_CLI", "figma-cli")
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")

SPECS = [
    {"name": "figma-ios-app-icon-styles", "func": "app_icon_styles", "node": "2402:17543",
     "set_name": "App Icon/iPhone", "subject": "App Icon styles", "expected": ["Custom", "System"]},
    {"name": "figma-ios-date-picker-styles", "func": "date_picker_styles", "node": "5442:1885",
     "set_name": "Date and time - Pickers", "subject": "date & time picker styles", "expected": ["Compact", "Inline"]},
    {"name": "figma-ios-header-prominence", "func": "header_prominence_levels", "node": "517:38042",
     "set_name": "Header", "subject": "Header prominence levels", "expected": ["Extra Prominent", "Nested", "Prominent"]},
]


def find(n, nid):
    if n.get("id") == nid:
        return n
    for c in n.get("children", []) or []:
        r = find(c, nid)
        if r:
            return r


def trimmed_dump(node_id):
    """A /files-shaped dump containing only the target node's subtree."""
    node = find(FULL["document"], node_id)
    canvas = {"id": "0:1", "name": "Components", "type": "CANVAS", "children": [node]}
    doc = {"id": "0:0", "name": "Document", "type": "DOCUMENT", "children": [canvas]}
    out = {k: FULL[k] for k in ("name", "lastModified", "version", "role", "editorType", "thumbnailUrl")}
    out.update({"document": doc, "components": {}, "componentSets": {}, "styles": {}, "schemaVersion": 0})
    return out


def w(path, content, ex=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(content)
    if ex:
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def gen(spec):
    t = f"{OUT_ROOT}/{spec['name']}"
    func, expected = spec["func"], spec["expected"]
    exp_lit = json.dumps(expected)
    # --- :empty fixture (trimmed subtree, same key) ---
    dump = f"/tmp/{spec['name']}_dump.json"
    json.dump(trimmed_dump(spec["node"]), open(dump, "w"))
    os.makedirs(f"{t}/environment/data/figma", exist_ok=True)
    subprocess.run([FIGMA_CLI, "seed", "import-file", dump, "--key", KEY, "--out", f"/tmp/{spec['name']}.db",
                    "--emit", f"{t}/environment/data/figma/fixture.json"], check=True)
    # --- codebase ---
    w(f"{t}/environment/codebase/ios_components/__init__.py", f"from .comp import {func}\n__all__ = [{func!r}]\n")
    w(f"{t}/environment/codebase/ios_components/comp.py", textwrap.dedent(f'''\
        """The {spec['subject']} defined in the design.

        Placeholder — the real values are the variants of the "{spec['set_name']}"
        component set in the Figma file, not here. Update to match the design.
        """
        from __future__ import annotations


        def {func}() -> list[str]:
            return []
    '''))
    visible = textwrap.dedent(f'''\
        """Visible, invariant-only check — shape only, never the values."""
        from ios_components import {func}

        def test_returns_list_of_names():
            s = {func}()
            assert isinstance(s, list) and len(s) >= 1
            assert all(isinstance(x, str) and x for x in s)
    ''')
    w(f"{t}/environment/codebase/tests/test_comp.py", visible)
    w(f"{t}/tests/trusted/test_comp.py", visible)
    w(f"{t}/tests/trusted/test_grade_comp.py", textwrap.dedent(f'''\
        """HIDDEN grader — the values only exist in the Figma design (the
        "{spec['set_name']}" component set variants). Order-insensitive."""
        from ios_components import {func}

        def test_matches_design():
            assert sorted({func}()) == {sorted(expected)!r}
    '''))
    # --- verifier ---
    w(f"{t}/tests/test.sh", textwrap.dedent('''\
        #!/usr/bin/env bash
        set -uo pipefail
        mkdir -p /logs/verifier 2>/dev/null || true
        HERE="$(cd "$(dirname "$0")" && pwd)"
        GRADE="/tmp/grade.$$"; mkdir -p "$GRADE"
        cp -r /app/ios_components "$GRADE/ios_components"
        cp "$HERE/trusted/test_comp.py" "$HERE/trusted/test_grade_comp.py" "$GRADE/"
        code_ok=0
        ( cd "$GRADE" && python3 -m pytest -q ) > /logs/verifier/pytest.log 2>&1 && code_ok=1
        echo "[verifier] code_ok=$code_ok"; tail -n 2 /logs/verifier/pytest.log 2>/dev/null || true
        reward=0; [ "$code_ok" = 1 ] && reward=1
        echo "$reward" > /logs/verifier/reward.txt 2>/dev/null || true
        echo "reward=$reward"; exit 0
    '''), ex=True)
    # --- oracle ---
    w(f"{t}/solution/solve.sh", textwrap.dedent(f'''\
        #!/usr/bin/env bash
        set -euo pipefail
        # (agent recovers via: figma-cli search "$FIGMA_FILE_KEY" "{spec['set_name']}" -> node {spec['node']}
        #  then figma-cli node "$FIGMA_FILE_KEY" {spec['node']} -> the variant names)
        cat > /app/ios_components/comp.py <<'PY'
        """The {spec['subject']} defined in the design."""
        from __future__ import annotations


        def {func}() -> list[str]:
            return {exp_lit}
        PY
        echo "oracle: wrote {spec['subject']}"
    '''), ex=True)
    # --- Dockerfile (thin agent) ---
    w(f"{t}/environment/Dockerfile", textwrap.dedent(f'''\
        # Agent (`main`) — thin figma-agent (figma-cli + figma-mcp, no server/seed source) + pytest + codebase.
        FROM ghcr.io/abundant-ai/figma-agent:latest
        RUN pip install --no-cache-dir pytest
        COPY codebase /app
        RUN ln -sf "$(command -v python3)" /usr/local/bin/python
        WORKDIR /app
        ENV FIGMA_API_URL=http://figma:3000 FIGMA_TOKEN=figma-clone-token FIGMA_FILE_KEY={KEY}
        ENTRYPOINT []
        CMD ["sleep", "infinity"]
    '''))
    # --- compose (variant switch) ---
    w(f"{t}/environment/docker-compose.yaml", textwrap.dedent(f'''\
        # empty<->prod-v1 by one line: FIGMA_SERVICE_IMAGE=ghcr.io/abundant-ai/figma-service:prod-v1
        services:
          main:
            platform: linux/amd64
            build: {{ context: ., dockerfile: Dockerfile }}
            image: ${{MAIN_IMAGE_NAME}}
            working_dir: /app
            environment:
              FIGMA_API_URL: http://figma:3000
              FIGMA_TOKEN: figma-clone-token
              FIGMA_FILE_KEY: {KEY}
            depends_on: {{ figma: {{ condition: service_healthy }} }}
          figma:
            image: ${{FIGMA_SERVICE_IMAGE:-ghcr.io/abundant-ai/figma-service:empty}}
            hostname: figma
            platform: linux/amd64
            environment: {{ FIGMA_FIXTURE: /srv/fixture.json }}
            volumes:
              - ./data/figma/fixture.json:/srv/fixture.json:ro
            healthcheck:
              test: ["CMD-SHELL", "curl -sf http://localhost:3000/health >/dev/null || exit 1"]
              interval: 5s
              timeout: 5s
              retries: 24
              start_period: 15s
    '''))
    # --- task.toml ---
    w(f"{t}/task.toml", textwrap.dedent(f'''\
        schema_version = "1.2"
        name = "figma-ios/{spec['name']}"
        description = "Real2sim task on the iOS and iPadOS 26 (Community) Figma corpus. The agent must use the figma tool to read the \\"{spec['set_name']}\\" component set and implement {func}() to return its variant values (the part after Size=/Type=/etc). Values exist only in the design. Hidden grader pins them (order-insensitive). Runs on :empty (mounted slice) or :prod-v1 (baked full corpus). nop=0, oracle=1."

        [metadata]
        category = "observability"
        source = "Figma Community: iOS and iPadOS 26 (Community), file {KEY}"
        failure_mode = "info-in-design-only"
        tags = ["figma", "figma-clone", "real2sim", "observability", "components", "variant-axis"]

        [agent]
        timeout_sec = 1200
        [verifier]
        timeout_sec = 180
        [environment]
        cpus = 2
        memory_mb = 4096
        storage_mb = 12288
        gpus = 0
        allow_internet = true
        workdir = "/app"
        build_timeout_sec = 2400

        [[environment.mcp_servers]]
        name = "figma"
        transport = "stdio"
        command = "figma-mcp"
    '''))
    # --- instruction ---
    w(f"{t}/instruction.md", textwrap.dedent(f'''\
        # Read the {spec['subject']} from the design

        We need the list of **{spec['subject']}** the design system defines, in code.

        - `/app/ios_components/comp.py` — `{func}()` should return that list. It returns `[]` now.

        The values are **in the Figma design, not the repo**. You have the `figma-cli`
        command and the `figma` MCP server. The file key is `{KEY}` (`$FIGMA_FILE_KEY`).

        ## What to do
        1. Find the component set named **"{spec['set_name']}"** in the design
           (`figma-cli search "$FIGMA_FILE_KEY" "{spec['set_name']}"`), then inspect its
           variants (`figma-cli node "$FIGMA_FILE_KEY" <node-id>`).
        2. Update `{func}()` to return each variant's value (the part after `=` in the
           variant name). Order doesn't matter.

        Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
    '''))
    print(f"  generated {spec['name']}  (set {spec['node']} -> {sorted(expected)})  fixture={os.path.getsize(t+'/environment/data/figma/fixture.json')}b")


if __name__ == "__main__":
    for s in SPECS:
        gen(s)
    print("done")
