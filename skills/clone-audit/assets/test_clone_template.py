"""
test_clone_template.py — parametrized pytest scaffold for clone-audit Phase 3 (R6).

Fill the four tables (ENDPOINTS / CLI_CASES / MCP_CASES / PARITY_CASES) from the Phase-2 coverage
matrix. Each capability should appear in ALL relevant tables so every endpoint, CLI command, and MCP
tool gets a happy + error path, plus a CLI<->MCP parity check. Leave passing tests in the clone's
tests/ so the next audit and the verifier reuse them.

Env:
  CLONE_BASE_URL   HTTP base of the running service (e.g. http://localhost:8080)
  CLONE_TOKEN      bearer/api token if the clone needs auth
  CLONE_CLI        CLI entrypoint name (e.g. "figma-cli", "jira", "sentry")
  CLONE_MCP_CMD    command that starts the MCP server over stdio (e.g. "figma-mcp")
  CLONE_STATE_PATH seed path that must NOT exist in the agent env (isolation test)
"""
import json, os, shutil, subprocess, urllib.request
import pytest

BASE  = os.environ.get("CLONE_BASE_URL", "http://localhost:8080")
TOKEN = os.environ.get("CLONE_TOKEN", "")
CLI   = os.environ.get("CLONE_CLI", "")
MCP   = os.environ.get("CLONE_MCP_CMD", "")


# ---- thin clients -----------------------------------------------------------
def http(method, path, body=None, token=TOKEN):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token: req.add_header("Authorization", f"Bearer {token}")
    if data:  req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:           # error paths land here on purpose
        raw = e.read()
        try: return e.code, json.loads(raw)
        except Exception: return e.code, raw.decode(errors="replace")


def run_cli(*args):
    out = subprocess.run([CLI, *args], capture_output=True, text=True)
    return out.returncode, out.stdout, out.stderr


def call_mcp_tool(tool, arguments):
    """Minimal stdio MCP client: initialize -> tools/call -> parse result."""
    proc = subprocess.Popen(MCP.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def send(obj): proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()
    def recv():    return json.loads(proc.stdout.readline())
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "audit", "version": "1"}}})
    recv()
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": tool, "arguments": arguments}})
    resp = recv()
    proc.terminate()
    return resp


def normalize(x):
    """Strip presentation so CLI text and MCP structured output can be compared."""
    if isinstance(x, str):
        try: x = json.loads(x)
        except Exception: return x.strip()
    return json.dumps(x, sort_keys=True)


# ---- tables to fill from the coverage matrix --------------------------------
# (method, path, body, expect_status)
ENDPOINTS = [
    # ("GET", "/v1/files/SEEDKEY", None, 200),
    # ("GET", "/v1/files/DOES-NOT-EXIST", None, 404),     # error path
]
# (cli_args, expect_rc)
CLI_CASES = [
    # (("files", "get", "SEEDKEY", "--json"), 0),
    # (("files", "get", "NOPE"), 2),                       # error path -> non-zero exit
]
# (tool, arguments, expect_error: bool)
MCP_CASES = [
    # ("figma_get_file", {"file_key": "SEEDKEY"}, False),
    # ("figma_get_file", {"file_key": "NOPE"}, True),      # error path
]
# capability -> (cli_args, (mcp_tool, mcp_args)) : same data both ways (R6.2)
PARITY_CASES = [
    # (("files", "get", "SEEDKEY", "--json"), ("figma_get_file", {"file_key": "SEEDKEY"})),
]


# ---- tests ------------------------------------------------------------------
@pytest.mark.parametrize("method,path,body,expect", ENDPOINTS)
def test_endpoint(method, path, body, expect):
    status, _ = http(method, path, body)
    assert status == expect, f"{method} {path} -> {status}, want {expect}"

@pytest.mark.parametrize("args,expect_rc", CLI_CASES)
def test_cli(args, expect_rc):
    rc, out, err = run_cli(*args)
    assert rc == expect_rc, f"{CLI} {' '.join(args)} -> rc {rc}, want {expect_rc}; stderr={err}"

@pytest.mark.parametrize("tool,arguments,expect_error", MCP_CASES)
def test_mcp(tool, arguments, expect_error):
    resp = call_mcp_tool(tool, arguments)
    is_error = "error" in resp or (resp.get("result", {}) or {}).get("isError", False)
    assert is_error == expect_error, f"{tool}({arguments}) error={is_error}, want {expect_error}"

@pytest.mark.parametrize("cli_args,mcp", PARITY_CASES)
def test_cli_mcp_parity(cli_args, mcp):
    _, cli_out, _ = run_cli(*cli_args)
    tool, args = mcp
    mcp_resp = call_mcp_tool(tool, args)
    content = (mcp_resp.get("result", {}) or {}).get("content", mcp_resp)
    assert normalize(cli_out) == normalize(content), "CLI and MCP disagree — surfaces have drifted (R3/R6.2)"

def test_isolation_no_seed_on_disk():
    """R6.3: the agent environment must not contain the seed/answer-key on disk."""
    state = os.environ.get("CLONE_STATE_PATH")
    if not state:
        pytest.skip("set CLONE_STATE_PATH to assert isolation")
    assert not os.path.exists(state), f"LEAK: {state} present — agent could read the answer key"

def test_world_building_tools_absent_from_agent():
    """R6.3: import/seed/hydrate must not be callable from the agent."""
    for op in ("seed", "import-state", "hydrate", "snapshot"):
        assert shutil.which(op) is None, f"world-building tool '{op}' on agent PATH"
