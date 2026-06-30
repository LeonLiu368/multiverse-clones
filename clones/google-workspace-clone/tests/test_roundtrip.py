"""Assessment-grade write->read round-trip (R5.2), end-to-end across all three
surfaces of the same capability: HTTP, then `gws-cli`, then `gws-mcp`. An event
created through one tool is observable through the others (one HTTP store)."""
from tests._helpers import call_mcp_tool, http, run_cli


def test_write_read_roundtrip_cross_surface(base_url, cli_env):
    # WRITE via raw HTTP
    st, created = http("POST", base_url, "/calendar/v3/calendars/primary/events",
                       body={"summary": "Cross-Surface RT",
                             "start": {"dateTime": "2026-09-12T09:00:00Z"},
                             "end": {"dateTime": "2026-09-12T10:00:00Z"},
                             "location": "HQ"})
    assert st == 200
    eid = created["id"]

    # READ back via CLI
    rc, out, err = run_cli(cli_env, "calendar", "get", eid)
    assert rc == 0, err
    import json
    assert json.loads(out)["summary"] == "Cross-Surface RT"

    # READ back via MCP
    is_err, payload = call_mcp_tool(cli_env, "gws_get_event", {"event_id": eid})
    assert not is_err and payload["location"] == "HQ"

    # and discoverable by query
    is_err, listing = call_mcp_tool(cli_env, "gws_list_events", {"q": "Cross-Surface"})
    assert not is_err and eid in [e["id"] for e in listing["items"]]
