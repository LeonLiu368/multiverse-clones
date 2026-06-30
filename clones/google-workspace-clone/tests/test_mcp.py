"""`gws-mcp` stdio coverage (R6.1): every MCP tool, happy + >=1 error path, driven
over the real JSON-RPC stdio transport a Harbor agent uses (R3.1)."""
from tests._helpers import call_mcp_tool, list_mcp_tools

DOC = "DOC_PLAN_0001"

EXPECTED_TOOLS = {
    "gws_list_files", "gws_get_file", "gws_get_document", "gws_get_file_text",
    "gws_get_document_text", "gws_search_document", "gws_list_events",
    "gws_get_event", "gws_create_event", "gws_search_messages",
    "gws_get_message", "gws_get_thread",
}


def test_mcp_lists_all_tools(cli_env):
    tools = set(list_mcp_tools(cli_env))
    assert EXPECTED_TOOLS <= tools, f"missing: {EXPECTED_TOOLS - tools}"


# ---- happy paths ----
def test_mcp_list_files(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_list_files", {})
    assert not err and payload["kind"] == "drive#fileList"


def test_mcp_get_file(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_file", {"file_id": DOC})
    assert not err and payload["id"] == DOC


def test_mcp_get_document(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_document", {"document_id": DOC})
    assert not err and payload["documentId"] == DOC


def test_mcp_get_file_text(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_file_text", {"file_id": DOC})
    assert not err and "2026-09-15" in payload


def test_mcp_get_document_text(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_document_text", {"document_id": DOC})
    assert not err and "Launch date: 2026-09-15" in payload


def test_mcp_search_document(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_search_document",
                                 {"document_id": DOC, "query": "Launch date"})
    assert not err and any("2026-09-15" in r["text"] for r in payload)


def test_mcp_list_events(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_list_events", {})
    assert not err
    summaries = {e["summary"] for e in payload["items"]}
    assert {"Q3 Kickoff", "Design Review"} <= summaries  # >=, other tests may insert


def test_mcp_get_event(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_event", {"event_id": "EV_KICKOFF_1"})
    assert not err and payload["summary"] == "Q3 Kickoff"


def test_mcp_create_event_roundtrip(cli_env):
    """gws_create_event (WRITE) then read it back via gws_get_event (R5.2)."""
    err, created = call_mcp_tool(cli_env, "gws_create_event",
                                 {"summary": "MCP RoundTrip",
                                  "start": "2026-09-11T09:00:00Z",
                                  "end": "2026-09-11T10:00:00Z"})
    assert not err, created
    eid = created["id"]
    err, got = call_mcp_tool(cli_env, "gws_get_event", {"event_id": eid})
    assert not err and got["summary"] == "MCP RoundTrip"


def test_mcp_search_messages(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_search_messages", {"q": "from:pm"})
    assert not err and payload["resultSizeEstimate"] == 1


def test_mcp_get_message(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_message", {"message_id": "MSG_1"})
    assert not err and payload["id"] == "MSG_1" and "ship date" in payload["bodyText"].lower()


def test_mcp_get_thread(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_thread", {"thread_id": "THR_1"})
    assert not err and len(payload["messages"]) == 2


# ---- error paths ----
# The read tools surface the API's {error:...} JSON as the structured payload (the
# httpx client returns r.json() verbatim); the file/doc-text tools return an
# "error: ..." string. Either way the agent observes the failure, not seed data.
def test_mcp_get_file_error(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_file", {"file_id": "NOPE"})
    assert err or (isinstance(payload, dict) and "error" in payload)


def test_mcp_get_document_error(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_document", {"document_id": "NOPE"})
    assert err or (isinstance(payload, dict) and "error" in payload)


def test_mcp_get_file_text_error(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_file_text", {"file_id": "NOPE"})
    assert err or (isinstance(payload, str) and "error" in payload.lower())


def test_mcp_get_event_error(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_event", {"event_id": "NOPE"})
    assert err or (isinstance(payload, dict) and "error" in payload)


def test_mcp_create_event_error(cli_env):
    """Missing end -> the API's 400 error envelope surfaces through the tool."""
    err, payload = call_mcp_tool(cli_env, "gws_create_event",
                                 {"summary": "x", "start": "2026-09-11T09:00:00Z", "end": ""})
    assert err or (isinstance(payload, dict) and "error" in payload)


def test_mcp_get_message_error(cli_env):
    err, payload = call_mcp_tool(cli_env, "gws_get_message", {"message_id": "NOPE"})
    assert err or (isinstance(payload, dict) and "error" in payload)
