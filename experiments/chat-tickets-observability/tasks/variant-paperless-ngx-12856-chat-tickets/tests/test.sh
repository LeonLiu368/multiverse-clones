#!/bin/bash
# Orchestration ONLY (split-harness policy). Reward computation lives in run_verifier.sh.
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
bash "$TESTS_DIR/stage_data.sh"     || true
bash "$TESTS_DIR/run_candidate.sh"  || true
bash "$TESTS_DIR/run_verifier.sh"
exit 0
