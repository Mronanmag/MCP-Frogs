#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_python_bin() {
  if [[ -n "${MCP_FROGS_PYTHON:-}" ]]; then
    echo "$MCP_FROGS_PYTHON"
    return 0
  fi

  local candidates=(
    "$ROOT_DIR/.venv/bin/python"
    "/opt/conda/envs/mcp_frogs/bin/python"
    "python3"
    "python"
  )

  local c
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done

  echo "[mcp-frogs] ERROR: no Python interpreter found for MCP server." >&2
  echo "Set MCP_FROGS_PYTHON=/path/to/python and retry." >&2
  return 1
}

MCP_PYTHON="$(resolve_python_bin)"
FROGS_PYTHON_BIN="${FROGS_PYTHON:-$MCP_PYTHON}"

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/mcp_server}"
export FROGS_PYTHON="$FROGS_PYTHON_BIN"

exec "$MCP_PYTHON" "$ROOT_DIR/mcp_server/server.py"
