"""PortWatch over Model Context Protocol.

The same tool registry the internal agents use, exposed to MCP clients with the
READ / SIMULATE / PROPOSE / EXECUTE boundary intact.
"""

from src.portwatch_os.mcp.server import (
    PROTOCOL_VERSION,
    SERVER_INFO,
    SERVER_INSTRUCTIONS,
    PortWatchMCPServer,
    Resource,
    build_server,
    main,
)

__all__ = [
    "PROTOCOL_VERSION", "SERVER_INFO", "SERVER_INSTRUCTIONS",
    "PortWatchMCPServer", "Resource", "build_server", "main",
]
