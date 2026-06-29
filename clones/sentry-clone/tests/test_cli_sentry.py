from __future__ import annotations

from .helpers import TestServer, json_out, run_sentry


def test_cli_smoke_for_every_command_group() -> None:
    with TestServer() as server:
        commands = [
            ["config", "check", "--json"],
            ["whoami", "--json"],
            ["org", "list", "--json"],
            ["projects", "list", "--org", "acme", "--json"],
            ["issues", "list", "--project", "payments-api", "--query", "is:unresolved", "--json"],
            ["issues", "get", "PAYMENTS-501", "--json"],
            ["issues", "events", "PAYMENTS-501", "--json"],
            ["issues", "latest-event", "PAYMENTS-501", "--json"],
            ["issues", "stacktrace", "PAYMENTS-501", "--json"],
            ["issues", "breadcrumbs", "PAYMENTS-501", "--json"],
            ["issues", "tags", "PAYMENTS-501", "--json"],
            ["issues", "suspect-commits", "PAYMENTS-501", "--json"],
            ["issues", "activity", "PAYMENTS-501", "--json"],
            ["issues", "comments", "PAYMENTS-501", "--json"],
            ["issues", "comment", "PAYMENTS-501", "--text", "cli comment", "--json"],
            ["issues", "assign", "PAYMENTS-501", "--team", "payments", "--json"],
            ["issues", "resolve", "PAYMENTS-501", "--in-release", "payments-api@2026.06.07.2", "--json"],
            ["issues", "ignore", "PAYMENTS-501", "--reason", "not actionable", "--json"],
            ["issues", "reopen", "PAYMENTS-501", "--json"],
            ["events", "get", "evt-1001-latest", "--project", "payments-api", "--json"],
            ["releases", "list", "--project", "payments-api", "--json"],
            ["releases", "get", "payments-api@2026.06.07.1", "--project", "payments-api", "--json"],
            ["releases", "commits", "payments-api@2026.06.07.1", "--project", "payments-api", "--json"],
            ["ownership", "list", "--project", "payments-api", "--json"],
        ]
        for command in commands:
            result = run_sentry(server.url, command)
            assert result.returncode == 0, (command, result.stderr, result.stdout)
            json_out(result)
