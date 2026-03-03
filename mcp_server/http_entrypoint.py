"""HTTP launcher for the MCP-Frogs server.

This keeps ``server.py`` unchanged for local stdio usage while exposing the same
FastMCP app over HTTP/SSE for container-to-container access.
"""

from server import mcp


if __name__ == "__main__":
    # Streamable HTTP transport is the easiest way to share an MCP server
    # across containers while keeping Claude Code isolated.
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
