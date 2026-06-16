## Your Task

**Issue Description**:

## Description

We need to implement a flexible coinbase address configuration system for the Bor consensus that allows transaction fees to be redirected to different addresses at specific block heights. This is particularly important for the Rio hardfork, where we need to redirect all transaction fees from block producers to a designated protocol address.

## Current Problem

Right now, transaction fees go directly to the validators who produce blocks. However, we need the ability to:
- Configure different fee recipient addresses that activate at specific block numbers
- Support the Rio hardfork requirement where fees should be redirected to a protocol-controlled address (0x000000000000000000000000000000000000ba5e) starting at a specific block
- Handle multiple transitions over time as the protocol evolves

## Expected Behavior

**Before Rio Hardfork:**
- Transaction fees should go to the validator who produces each block
- Validators accumulate fees in their balances normally

**At and After Rio Hardfork:**
- All transaction fees should be redirected to the configured Rio coinbase address
- Validators should no longer receive any transaction fees
- The Rio address should start accumulating all fees from the activation block onward

**Configuration System:**
- Support a mapping of block numbers to coinbase addresses
- When no configuration exists, default to the zero address
- Allow multiple sequential transitions (e.g., different addresses at blocks 1000, 5000, 10000)
- Each address should remain active until the next configured transition
- The system should handle the genesis block (block 0) correctly

## Why This Matters

This feature is critical for protocol upgrades like Rio that change the economic model. It gives us the flexibility to redirect fees for protocol development, treasury management, or other governance decisions without requiring validators to manually send fees elsewhere.
The application source code is checked out at `/app/repo`.

---

## Available Tools

This is an observability task — use the observability and collaboration tools to debug.

### Logs / dashboards (Grafana-compatible)
```bash
gcx logs query '{service="bor-node"}'
gcx logs query '{service="bor-node"} |= "coinbase"'
```
### Issue tracker
```bash
linear issue list
linear issue search "coinbase"
```
### Team chat
```bash
slack channels list
slack messages search "Rio"
```

Correlate these signals, fix the root cause in `/app/repo`, and validate against the
project's own test suite. Do not modify the test suite to make it pass.
