#!/bin/bash
# Deterministic verifier for the read-only recall task. Reads the agent's answer
# file off the workdir and checks it recovered the agreed rate limit + burst that
# live ONLY in the Discord #engineering discussion. Binary reward in {0.0, 1.0}
# written to $REWARD_DIR/reward.txt.
#
# Full reward (1.0) iff /workspace/answer.txt contains BOTH:
#     rate=120   (agreed per-API-key requests/min)
#     burst=20   (agreed burst allowance)
# tolerating surrounding whitespace and case. 0.0 otherwise.
#
# Honors a REWARD_DIR override so it runs locally (no container); in-container it
# writes /logs/verifier/reward.txt. No Discord API read is needed to grade — the
# needle only had to be RECOVERED by the agent; the graded artifact is answer.txt.
set -uo pipefail
REWARD_DIR="${REWARD_DIR:-/logs/verifier}"
mkdir -p "$REWARD_DIR"
export REWARD_DIR
WORKDIR="${WORKDIR:-/workspace}"
export WORKDIR

python3 - <<'PY'
import os, re, sys

REWARD = os.path.join(os.environ.get("REWARD_DIR", "/logs/verifier"), "reward.txt")
WORKDIR = os.environ.get("WORKDIR", "/workspace")
EXPECT_RATE = 120
EXPECT_BURST = 20

def fail(msg, score=0.0):
    print("VERIFY:", msg)
    open(REWARD, "w").write(str(score))
    sys.exit(0)

ans_path = os.path.join(WORKDIR, "answer.txt")
try:
    text = open(ans_path).read()
except OSError as e:
    fail(f"answer.txt unreadable: {e}")

def field(name):
    m = re.search(rf"(?im)^\s*{name}\s*=\s*(\d+)\s*$", text)
    return int(m.group(1)) if m else None

rate = field("rate")
burst = field("burst")
if rate is None:
    fail("no 'rate=<N>' line found in answer.txt")
if burst is None:
    fail("no 'burst=<N>' line found in answer.txt")
if rate != EXPECT_RATE:
    fail(f"rate is {rate}, expected {EXPECT_RATE}")
if burst != EXPECT_BURST:
    fail(f"burst is {burst}, expected {EXPECT_BURST}")

print("VERIFY: answer.txt recovered the agreed rate limit + burst")
open(REWARD, "w").write("1.0")
PY
