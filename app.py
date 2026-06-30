import os
import config
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from auth_provider import InMemoryOAuthProvider
from auth0_verifier import Auth0TokenVerifier

auth_provider = None
auth_settings = None
token_verifier = None

public_url = os.environ.get("MCP_PUBLIC_URL", "https://tools.ananselabs.org")

if os.environ.get("MCP_ENABLE_AUTH0", "false").lower() == "true":
    auth0_domain = os.environ.get("AUTH0_DOMAIN", "dev-0rvyw5vo8eu0rdbp.uk.auth0.com")
    auth0_audience = os.environ.get("AUTH0_AUDIENCE", "https://dev-0rvyw5vo8eu0rdbp.uk.auth0.com/api/v2/")
    
    token_verifier = Auth0TokenVerifier(domain=auth0_domain, audience=auth0_audience)
    auth_settings = AuthSettings(
        issuer_url=f"https://{auth0_domain}/",
        resource_server_url=public_url,
        required_scopes=["mcp"]
    )
elif os.environ.get("MCP_ENABLE_OAUTH", "false").lower() == "true":
    auth_provider = InMemoryOAuthProvider()
    
    auth_settings = AuthSettings(
        issuer_url=public_url,
        resource_server_url=public_url,
        required_scopes=["mcp"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp"],
            default_scopes=["mcp"]
        ),
        revocation_options=RevocationOptions(enabled=True)
    )

mcp = FastMCP(
    "ananse-mcp",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8000")),
    sse_path="/",
    auth_server_provider=auth_provider,
    token_verifier=token_verifier,
    auth=auth_settings,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=os.environ.get("MCP_DNS_REBINDING_PROTECTION", "true").lower() == "true",
        allowed_hosts=[h.strip() for h in os.environ.get("MCP_PUBLIC_HOSTNAME", "localhost,127.0.0.1,tools.ananselabs.org,*.ananselabs.org").split(",") if h.strip()],
    ),
)

class SSESessionRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope["method"]
            query_string = scope.get("query_string", b"").decode("utf-8")
            
            # 1. Route GET handshakes and normalize OAuth discovery endpoints
            if method == "GET":
                if path in {"/sse", "/mcp"}:
                    scope["path"] = "/"
                elif ".well-known/oauth-protected-resource" in path:
                    scope["path"] = "/.well-known/oauth-protected-resource"
                elif ".well-known/oauth-authorization-server" in path or ".well-known/openid-configuration" in path:
                    scope["path"] = "/.well-known/oauth-authorization-server"
            
            # 2. Route POST messages to either "/messages/" or the "/mcp" stateless route
            elif method == "POST":
                if path in {"/", "/sse", "/mcp"}:
                    if "session_id=" in query_string:
                        scope["path"] = "/messages/"
                    else:
                        scope["path"] = "/mcp"
                        
        await self.app(scope, receive, send)

original_sse_app = mcp.sse_app
def custom_sse_app(*args, **kwargs):
    app = original_sse_app(*args, **kwargs)
    
    # Mount/append the stateless /mcp route from the streamable HTTP app
    try:
        http_app = mcp.streamable_http_app()
        mcp_route = next(r for r in http_app.routes if getattr(r, "path", None) == "/mcp")
        app.routes.append(mcp_route)
    except Exception as e:
        import sys
        print(f"Warning: Failed to import stateless /mcp route: {e}", file=sys.stderr)
        
    return SSESessionRewriteMiddleware(app)
mcp.sse_app = custom_sse_app
