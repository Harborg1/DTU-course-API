"""Compatibility exports for the DTU Course API MCP server.

The HTTP transport is created by :mod:`app.main` for each FastAPI lifespan.
Keeping the implementation in ``server.py`` avoids registering two different
sets of MCP tools.
"""

from app.mcp_server.server import ALL_TOOLS, create_mcp_transport, transport_security_for_url

__all__ = ["ALL_TOOLS", "create_mcp_transport", "transport_security_for_url"]
