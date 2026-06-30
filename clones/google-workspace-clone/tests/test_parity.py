"""CLI<->MCP parity (R6.2/R3.3): for each capability, the `gws-cli` command and the
matching `gws-mcp` tool return the same underlying data. Proves the two surfaces are
thin clients of one API and have not drifted."""
import pytest

from tests._helpers import call_mcp_tool, norm, run_cli

DOC = "DOC_PLAN_0001"

# capability -> (cli_args, (mcp_tool, mcp_args))
PARITY = [
    ("drive_list", ("drive", "ls", "-q", "name contains 'Launch'"),
     ("gws_list_files", {"q": "name contains 'Launch'"})),
    ("drive_get", ("drive", "get", DOC),
     ("gws_get_file", {"file_id": DOC})),
    ("docs_get", ("docs", "get", DOC),
     ("gws_get_document", {"document_id": DOC})),
    ("docs_text", ("docs", "text", DOC),
     ("gws_get_document_text", {"document_id": DOC})),
    ("calendar_list", ("calendar", "events", "-q", "LaTeX"),
     ("gws_list_events", {"q": "LaTeX"})),
    ("gmail_search", ("gmail", "search", "from:pm"),
     ("gws_search_messages", {"q": "from:pm"})),
]


@pytest.mark.parametrize("cap,cli_args,mcp", PARITY, ids=[p[0] for p in PARITY])
def test_cli_mcp_parity(cli_env, cap, cli_args, mcp):
    rc, cli_out, err = run_cli(cli_env, *cli_args)
    assert rc == 0, err
    tool, args = mcp
    is_err, payload = call_mcp_tool(cli_env, tool, args)
    assert not is_err, payload
    assert norm(cli_out) == norm(payload), \
        f"{cap}: CLI and MCP disagree — surfaces have drifted (R3.3/R6.2)"


def test_parity_error_envelope(cli_env):
    """A 404 must look the same from both surfaces (CLI exits non-zero; MCP carries
    the same {error:...} body)."""
    rc, _, err = run_cli(cli_env, "drive", "get", "NOPE")
    assert rc != 0
    is_err, payload = call_mcp_tool(cli_env, "gws_get_file", {"file_id": "NOPE"})
    assert isinstance(payload, dict) and payload.get("error", {}).get("status") == "NOT_FOUND"
