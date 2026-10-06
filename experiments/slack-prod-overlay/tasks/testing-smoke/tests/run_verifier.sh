#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if python3 "$TESTS_DIR/verify.py"; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
echo "reward=$(cat /logs/verifier/reward.txt)"
