## Your Task

**Issue Description**:

## Description

The blockchain implementation must handle Bor-specific state-sync receipts in eth/69 messages.
These receipts are separate from normal transaction receipts and must be processed, stored, and transmitted correctly during snap sync.

Currently, Bor receipts are not separated from normal receipts, causing errors in receipt handling, storage, and entwork communication

## Expected Behavior

The system should:

- Separte normal trnasaction receipts from state-sync receipts when processing block data.
- Store state-sync receipts independently from normal receipts in the database.
- Derive the cumulative gas used for state-sync receipts based on proceding normal receipts, unless already non-zero.
- Include sprint end blocks in receipt queues when sprint-based handling is enabled, even if receipt roots are empty.
- Encode receipts for eth/69 network messages correctly for all scenarios: only normal receipts, only state-sync receipts, or both together.
- Exclude state-sync receipts from receipt root calculations when required.
- Preserve receipt data integrity during storage and encoding/decoding cycles for both normal and state-sync receipts.

## Additional Context

Bor's state-sync mechanism introduces receipts that don't follow the standard Ethereum receipt model. These receipts need to be:
- Snap sync nodes persist Bor receipts without executing transactions.
- Network messages are compliant with eth/69 protocol.
- Future forks can include Bor receipts in receipt roots without breaking backward compatibility.

The application source code is checked out at `/app/repo`.

---

## Available Tools

This is an observability task — you should use the observability and collaboration tools to
debug and understand the issue.

### Logs / dashboards (Grafana-compatible)
Query the node's logs and dashboards with the `gcx` CLI or the `grafana` MCP server
(`mcp-grafana`):
```bash
gcx logs query '{service="bor-node"}'                 # node logs
gcx logs query '{service="bor-node"} |= "receipt"'    # filter to receipt-handling lines
gcx dashboards list
```

### Issue tracker
Search the project's issues with the `linear` (or `jira`) CLI:
```bash
linear issue list
linear issue search "receipt"
```

### Team chat
Read the community channel with the `slack` CLI (or the `slack` MCP server):
```bash
slack channels list
slack messages search "state-sync"
```

Correlate these signals to localize the failure, then implement the fix in `/app/repo`.
Validate your change against the project's own test suite. Do not modify the test suite to
make it pass.
