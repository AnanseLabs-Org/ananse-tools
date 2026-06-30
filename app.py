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

class SSESessionRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/":
            query_string = scope.get("query_string", b"").decode("utf-8")
            if "session_id=" in query_string:
                scope["path"] = "/messages/"
        await self.app(scope, receive, send)

original_sse_app = mcp.sse_app
def custom_sse_app(*args, **kwargs):
    app = original_sse_app(*args, **kwargs)
    return SSESessionRewriteMiddleware(app)
mcp.sse_app = custom_sse_app
