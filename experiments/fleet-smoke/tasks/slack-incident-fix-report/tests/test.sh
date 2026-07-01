#!/bin/bash
# Orchestration only — delegates the deterministic check to run_verifier.sh.
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
bash "$TESTS_DIR/run_verifier.sh"
exit 0
