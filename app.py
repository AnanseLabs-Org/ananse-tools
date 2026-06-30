import os
import config
import fastmcp
from fastmcp import FastMCP
from fastmcp.server.auth.providers.auth0 import Auth0Provider

# Configure settings globally
fastmcp.settings.sse_path = "/"
fastmcp.settings.message_path = "/messages/"

auth_provider = None

if os.environ.get("MCP_ENABLE_AUTH0", "false").lower() == "true":
    auth0_domain = os.environ.get("AUTH0_DOMAIN")
    auth0_client_id = os.environ.get("AUTH0_CLIENT_ID")
    auth0_client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
    auth0_audience = os.environ.get("AUTH0_AUDIENCE")
    public_url = os.environ.get("MCP_PUBLIC_URL")

    if not all([auth0_domain, auth0_client_id, auth0_client_secret, auth0_audience, public_url]):
        raise RuntimeError("Missing required Auth0 or public URL configurations in environment")

    auth_provider = Auth0Provider(
        config_url=f"https://{auth0_domain}/.well-known/openid-configuration",
        client_id=auth0_client_id,
        client_secret=auth0_client_secret,
        audience=auth0_audience,
        base_url=public_url,
    )

mcp = FastMCP("ananse-mcp", auth=auth_provider)

class SSESessionRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope["method"]
            
            # Normalize openid-configuration to oauth-authorization-server
            if method == "GET":
                if ".well-known/openid-configuration" in path:
                    scope["path"] = "/.well-known/oauth-authorization-server"
                    
        await self.app(scope, receive, send)

original_http_app = mcp.http_app
def custom_http_app(*args, **kwargs):
    # Enforce transport="sse" if not specified, since we run on SSE
    if "transport" not in kwargs:
        kwargs["transport"] = "sse"
    app = original_http_app(*args, **kwargs)
    return SSESessionRewriteMiddleware(app)
mcp.http_app = custom_http_app

# Add a protected tool to test authentication
@mcp.tool
async def get_token_info() -> dict:
    """Returns information about the Auth0 token."""
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()

    if not token:
        return {"error": "No token provided"}

    return {
        "issuer": token.claims.get("iss") if token.claims else None,
        "audience": token.claims.get("aud") if token.claims else None,
        "scope": token.claims.get("scope") if token.claims else None,
        "subject": token.subject,
        "client_id": token.client_id
    }
