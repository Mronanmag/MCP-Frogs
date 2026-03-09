#!/usr/bin/env bash
# All-in-one entrypoint: start the MCP server in the background, then exec
# the requested command (default: claude).
#
# Usage (via docker compose):
#   docker compose run --rm all-in-one          # starts MCP + claude (default)
#   docker compose run --rm all-in-one bash     # starts MCP + interactive shell
#
# Signal handling:
#   tini (PID 1) forwards signals to this script's direct child.
#   After "exec $@", the child becomes the CMD process (claude or bash).
#   The background MCP server is adopted by tini; it is terminated when
#   the container stops (i.e., when the foreground CMD exits).
set -euo pipefail

MCP_PORT="${MCP_PORT:-8000}"
MCP_HEALTH_URL="http://localhost:${MCP_PORT}/health"
WAIT_SECONDS=60

# ── Start MCP server in the background ────────────────────────────────────────
echo "[mcp-frogs] Starting MCP server (mcp_frogs env, port ${MCP_PORT})..." >&2
micromamba run -n mcp_frogs python /app/mcp_server/http_entrypoint.py &
MCP_PID=$!

# ── Wait for the health endpoint to respond ───────────────────────────────────
echo "[mcp-frogs] Waiting for MCP server to be ready (up to ${WAIT_SECONDS}s)..." >&2
for i in $(seq 1 "${WAIT_SECONDS}"); do
    if curl -fs "${MCP_HEALTH_URL}" > /dev/null 2>&1; then
        echo "[mcp-frogs] MCP server ready at ${MCP_HEALTH_URL}." >&2
        break
    fi
    # Abort early if the server process died
    if ! kill -0 "${MCP_PID}" 2>/dev/null; then
        echo "[mcp-frogs] ERROR: MCP server exited unexpectedly. Check logs above." >&2
        exit 1
    fi
    sleep 1
done

# Final check: if the loop exhausted without the server responding, warn but continue
if ! curl -fs "${MCP_HEALTH_URL}" > /dev/null 2>&1; then
    echo "[mcp-frogs] WARNING: MCP server did not respond within ${WAIT_SECONDS}s." \
         "Continuing anyway — Claude Code will retry the connection." >&2
fi

# ── Exec the requested command (replaces this shell) ─────────────────────────
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec bash -l
fi
