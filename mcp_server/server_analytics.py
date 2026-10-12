"""Compatibility entry point. Analytics is included in the primary billing server."""
from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)
