#!/bin/bash
# Deterministic verifier: reads task state back THROUGH the Discord API (never off
# disk) and writes a reward in [0,1] to $REWARD_DIR/reward.txt.
#
# Grades the write->read round-trip + the code fix:
#   1. checkout-service/config.py sets PRICING_CACHE_TTL == 300 (the agreed value)
#   2. a message in the guild's #deploys channel (read back via the API) mentions
#      BOTH "INC-4471" and "300", authored by the bot (the agent).
# Both required for full reward (1.0); 0.0 otherwise.
set -uo pipefail
REWARD_DIR="${REWARD_DIR:-/logs/verifier}"
mkdir -p "$REWARD_DIR"
export REWARD_DIR
WORKDIR="${WORKDIR:-/workspace}"
export WORKDIR

python3 - <<'PY'
import os, re, sys
from discordclone.client import DiscordClient, DiscordAPIError

REWARD = os.path.join(os.environ.get("REWARD_DIR", "/logs/verifier"), "reward.txt")
WORKDIR = os.environ.get("WORKDIR", "/workspace")
AGREED_TTL = 300

def fail(msg, score=0.0):
    print("VERIFY:", msg)
    open(REWARD, "w").write(str(score))
    sys.exit(0)

# 1. code fix — PRICING_CACHE_TTL restored to the agreed value.
cfg_path = os.path.join(WORKDIR, "checkout-service", "config.py")
try:
    src = open(cfg_path).read()
except OSError as e:
    fail(f"config.py unreadable: {e}")
m = re.search(r"^\s*PRICING_CACHE_TTL\s*=\s*(\d+)", src, re.M)
if not m:
    fail("PRICING_CACHE_TTL assignment not found in config.py")
if int(m.group(1)) != AGREED_TTL:
    fail(f"PRICING_CACHE_TTL is {m.group(1)}, expected {AGREED_TTL}")

# 2. round-trip — the remediation notice read back through the Discord API.
c = DiscordClient()
try:
    me = c.me()
    guilds = c.my_guilds()
except DiscordAPIError as e:
    fail(f"discord API unreachable: {e}")
if not guilds:
    fail("bot is in no guilds")
guild_id = guilds[0]["id"]

channels = c.get_guild_channels(guild_id)
deploys = next((ch for ch in channels if ch.get("name") == "deploys"), None)
if not deploys:
    fail("#deploys channel not found")

msgs = c.get_messages(deploys["id"], limit=100)
bot_id = me["id"]
hit = None
for msg in msgs:
    content = msg.get("content", "")
    if (msg.get("author", {}).get("id") == bot_id
            and "INC-4471" in content and str(AGREED_TTL) in content):
        hit = msg
        break
if hit is None:
    fail("no bot message in #deploys mentioning both INC-4471 and the restored TTL")

print("VERIFY: all checks passed (config fixed + remediation posted & read back)")
open(REWARD, "w").write("1.0")
PY
