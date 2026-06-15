#!/usr/bin/env bash
# Oracle: patch ratelimit/bucket.py with the agreed load-test configuration.
# CAPACITY=100, REFILL_RATE=10.0, INITIAL_TOKENS=100, OVERDRAFT_ALLOWANCE=0
set -euo pipefail

python3 - << 'PY'
import re, pathlib

p = pathlib.Path("/workspace/ratelimit/bucket.py")
src = p.read_text()
src = re.sub(r'CAPACITY\s*=\s*\d+',            'CAPACITY = 100',           src)
src = re.sub(r'REFILL_RATE\s*=\s*[\d.]+',      'REFILL_RATE = 10.0',       src)
src = re.sub(r'INITIAL_TOKENS\s*=\s*\d+',      'INITIAL_TOKENS = 100',     src)
src = re.sub(r'OVERDRAFT_ALLOWANCE\s*=\s*\d+', 'OVERDRAFT_ALLOWANCE = 0',  src)
p.write_text(src)
print("oracle: updated ratelimit/bucket.py")
PY
