"""Thin test clients: raw HTTP, the `gws-cli` subprocess, and a minimal stdio MCP
client that drives the `gws-mcp` server exactly as a Harbor agent would."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def http(method, base, path, body=None, token="test-token"):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw or b"null")
            except Exception:
                return r.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def run_cli(env, *args):
    """Run `gws-cli <args>` via the installed console script in this interpreter env."""
    out = subprocess.run([sys.executable, "-m", "gwsclone.cli.main", *args],
                         capture_output=True, text=True, env=env)
    return out.returncode, out.stdout, out.stderr


def call_mcp_tool(env, tool, arguments):
    """Minimal stdio MCP client: initialize -> tools/call -> parse the result.

    Returns (is_error, payload) where payload is the parsed structured/text result.
    """
    proc = subprocess.Popen([sys.executable, "-m", "gwsclone.mcp.server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, env=env)

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line else {}

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "test", "version": "1"}}})
        recv()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": tool, "arguments": arguments}})
        resp = recv()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    if "error" in resp:
        return True, resp["error"]
    result = resp.get("result", {}) or {}
    is_error = bool(result.get("isError", False))
    payload = _extract(result)
    return is_error, payload


def list_mcp_tools(env):
    proc = subprocess.Popen([sys.executable, "-m", "gwsclone.mcp.server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, env=env)

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line else {}

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "test", "version": "1"}}})
        recv()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        resp = recv()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    return [t["name"] for t in resp.get("result", {}).get("tools", [])]


def _extract(result: dict):
    """Prefer structuredContent; else parse the text content block."""
    if "structuredContent" in result:
        sc = result["structuredContent"]
        # FastMCP wraps scalar/list returns as {"result": ...}
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    content = result.get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    blob = "\n".join(texts)
    try:
        return json.loads(blob)
    except Exception:
        return blob


def norm(x):
    """Strip presentation so CLI text and MCP structured output compare equal."""
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except Exception:
            return x.strip()
    return json.dumps(x, sort_keys=True)
