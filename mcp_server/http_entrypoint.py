"""HTTP launcher for the MCP-Frogs server.

Dual-transport design
---------------------
Both MCP transports are served on the same port so any Claude Code version
can connect without image rebuilds:

  POST /mcp        → Streamable HTTP  (Claude Code ≥ 2.1 / MCP SDK ≥ 1.9)
  GET  /sse        → SSE legacy       (Claude Code < 2.1 / older clients)
  POST /messages   → SSE message POST (companion to GET /sse)
  GET  /health     → Docker HEALTHCHECK — returns {"status":"ok"}

Recommended .mcp.json entry (preferred transport):
  {"type": "http", "url": "http://mcp-server:8000/mcp"}  ← Streamable HTTP
  {"url": "http://mcp-server:8000/sse"}                   ← SSE fallback

Key design note
---------------
streamable_http_app() creates a Starlette app whose lifespan initialises
the StreamableHTTPSessionManager task group.  When routes from both apps
are merged naively into a new Starlette instance that lifespan is lost,
causing "Task group is not initialized" (HTTP 500).

Fix: build a combined lifespan that calls session_manager.run() explicitly,
then wire all routes (SSE + Streamable HTTP + /health) into one app with
that combined lifespan.

Environment variables
---------------------
MCP_HOST                             default: 0.0.0.0
MCP_PORT                             default: 8000
MCP_DISABLE_DNS_REBINDING_PROTECTION default: 1 (protection disabled in Docker)
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from server import mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _health(request: Request) -> Response:
    """Lightweight liveness probe used by Docker HEALTHCHECK."""
    return JSONResponse({"status": "ok", "server": "mcp-frogs"})


# ---------------------------------------------------------------------------
# Build combined ASGI app (SSE + Streamable HTTP + /health)
# ---------------------------------------------------------------------------

def build_app() -> Starlette:
    """
    Expose SSE (/sse, /messages), Streamable HTTP (/mcp), and /health on
    one Starlette application.

    The StreamableHTTPSessionManager requires its .run() context manager to
    be active (it sets up the anyio task group).  We call it inside the
    combined lifespan so it is properly initialised before any /mcp request
    arrives.
    """
    # Disable strict host-header checks for Docker-internal service names.
    if _as_bool(os.getenv("MCP_DISABLE_DNS_REBINDING_PROTECTION", "1")):
        try:
            mcp.settings.transport_security.enable_dns_rebinding_protection = False
        except AttributeError:
            pass  # SDK versions without transport_security

    # Build sub-apps — this lazily creates the session_manager for HTTP.
    sse_sub_app  = mcp.sse_app()              # /sse  + /messages
    http_sub_app = mcp.streamable_http_app()  # /mcp

    # The session_manager is created (lazily) inside streamable_http_app().
    session_manager = mcp.session_manager  # type: ignore[attr-defined]

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        """Start the Streamable HTTP session manager for the app lifetime."""
        async with session_manager.run():
            yield

    # http_sub_app exposes a Mount('/mcp', app=handle_asgi) which causes a
    # 307 redirect to /mcp/ for clients that send POST /mcp.  Unwrap the inner
    # ASGI callable and re-expose it as an explicit Route so no redirect occurs.
    mcp_mount = http_sub_app.routes[0]   # Mount('/mcp', app=<asgi fn>)
    # Guard against future SDK changes that drop the `.app` attribute.
    _handle_mcp_asgi = getattr(mcp_mount, "app", mcp_mount)  # raw ASGI callable

    async def mcp_endpoint(request: Request) -> Response:
        """Proxy to the Streamable HTTP ASGI handler without redirect."""
        scope = request.scope
        # Starlette Route strips the matched prefix; restore the full path so
        # the inner handler sees /mcp (it does not rely on path — but be safe).
        scope = {**scope, "path": "/mcp", "root_path": ""}
        return await _handle_mcp_asgi(scope, request.receive, request._send)

    # Merge all routes: /health first, then /mcp, then /sse + /messages.
    combined_routes = (
        [Route("/health", _health),
         Route("/mcp", mcp_endpoint, methods=["GET", "POST", "DELETE"])]
        + list(sse_sub_app.routes)    # /sse, /messages
    )

    return Starlette(routes=combined_routes, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    print(
        f"[mcp-frogs] MCP server starting on {host}:{port}\n"
        f"  Streamable HTTP  : http://{host}:{port}/mcp   (Claude Code ≥ 2.1)\n"
        f"  SSE legacy       : http://{host}:{port}/sse   (Claude Code < 2.1)\n"
        f"  Health check     : http://{host}:{port}/health",
        file=sys.stderr,
        flush=True,
    )

    uvicorn.run(
        build_app(),
        host=host,
        port=port,
        log_level="info",
    )
