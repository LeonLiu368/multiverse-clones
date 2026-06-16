## Your Task

**Issue Description**:

## Description

We need to implement proper Data Availability (DA) footprint tracking and enforcement in block
mining for the Jovian fork. Currently, block construction only considers transaction gas limits,
but with the Jovian upgrade, we need to account for the additional overhead of data availability
requirements.

## Expected Behavior

When the Jovian fork is active:
- Block mining should calculate and enforce DA footprint limits based on the size of transaction data
- Total block gas usage should include both transaction gas AND DA overhead (calculated as DA size multiplied by a scalar)
- Transactions that would push the block over the DA footprint limit should be excluded from the block
- The miner should pack exactly as many transactions as fit within the DA constraints
- Deposit transactions should not count toward DA footprint calculations

For earlier forks (Isthmus and before):
- Traditional gas accounting should continue to work (block gas = sum of transaction gas only)
- No DA footprint enforcement

## Additional Requirements

- Block generation needs to handle the full set of modern parameters: parent hash, timestamp,
  withdrawals, beacon root, gas limit, deposits, and EIP-1559 parameters
- The system must support beacon consensus alongside existing engines
- EIP-1559 parameters must be validated (rejecting zero denominators)

The application source code is checked out at `/app/repo`.

---

## Available Tools

This is an observability task — you should use the observability and collaboration tools to
debug and understand the issue.

### Logs / dashboards (Grafana-compatible)
```bash
gcx logs query '{service="op-geth"}'
gcx logs query '{service="op-geth"} |= "DA"'
```

### Issue tracker
```bash
linear issue list
linear issue search "footprint"
```

### Team chat
```bash
slack channels list
slack messages search "jovian"
```

Correlate these signals, fix the root cause in `/app/repo`, and validate against the project's
own test suite. Do not modify the test suite to make it pass.
