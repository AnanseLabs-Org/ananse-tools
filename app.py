import os
import config
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "ananse-mcp",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8000")),
    sse_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=os.environ.get("MCP_DNS_REBINDING_PROTECTION", "true").lower() == "true",
        allowed_hosts=[h.strip() for h in os.environ.get("MCP_PUBLIC_HOSTNAME", "localhost,127.0.0.1").split(",") if h.strip()],
    ),
)
