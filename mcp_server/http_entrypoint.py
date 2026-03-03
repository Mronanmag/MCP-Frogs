"""HTTP launcher for the MCP-Frogs server.

This entrypoint exposes FastMCP with the legacy SSE transport (`/sse` +
`/messages`) for compatibility with Claude Code 2.1.x.
"""

import os

from server import mcp


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    mcp.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.getenv("MCP_PORT", "8000"))

    # In docker-compose, requests may use service hostnames (e.g. mcp-server).
    # Disable strict host-header checks unless explicitly re-enabled.
    if _as_bool(os.getenv("MCP_DISABLE_DNS_REBINDING_PROTECTION", "1")):
        mcp.settings.transport_security.enable_dns_rebinding_protection = False

    # Claude Code 2.1.x expects SSE endpoints, not streamable-http sessions.
    mcp.run(transport="sse")
