#!/bin/bash
# Harbor verifier entrypoint — orchestration only; delegates the deterministic check.
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
bash "$TESTS_DIR/run_verifier.sh"
exit 0
