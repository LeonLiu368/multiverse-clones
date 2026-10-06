#!/usr/bin/env bash
# Oracle: read the greeting from the Figma file and return the name it introduces.
set -euo pipefail
# (An agent recovers this with: figma-cli text "$FIGMA_FILE_KEY" -> "Hello World! My name is Jaquavious")
cat > /app/whois/whois.py <<'PY'
"""The name introduced by the greeting in the design file."""

from __future__ import annotations


def greeting_name() -> str:
    return "Jaquavious"
PY
echo "oracle: wrote greeting name"
