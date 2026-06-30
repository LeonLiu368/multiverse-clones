"""aws-mcp: an MCP server exposing the same AWS surface the agent's CLI uses.

The capability functions live in :mod:`aws_clone.mcp.tools` as plain boto3
thin-clients against ``AWS_ENDPOINT_URL`` (the *exact* LocalStack endpoint the
``aws``/``awslocal`` CLI talks to) plus the token-gated admin reads the
``aws-clonectl`` CLI uses. ``server.py`` only wraps those functions with
FastMCP, so the CLI and MCP can never drift: one capability -> one boto3 call
(or one admin HTTP read) -> one CLI path -> one MCP tool.
"""
