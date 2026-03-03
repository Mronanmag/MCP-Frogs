#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MCP_PYTHON="${MCP_FROGS_PYTHON:-python3}"
FROGS_PYTHON_BIN="${FROGS_PYTHON:-$MCP_PYTHON}"

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/mcp_server}"
export FROGS_PYTHON="$FROGS_PYTHON_BIN"

exec "$MCP_PYTHON" "$ROOT_DIR/mcp_server/server.py"
