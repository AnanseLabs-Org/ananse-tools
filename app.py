import os
from typing import Any, Sequence

import fastmcp
import inspect
from fastmcp import FastMCP
from fastmcp.server import create_proxy
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider
from fastmcp.client.transports.sse import SSETransport
from fastmcp.server.dependencies import get_access_token
from mcp.types import ToolAnnotations
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from middleware import KeycloakRoleMiddleware


# ── Global fastmcp settings ─────────────────────────────────────────────────
fastmcp.settings.sse_path = "/"
fastmcp.settings.message_path = "/messages/"


# ── Keycloak authentication provider ────────────────────────────────────────
from fastmcp.server.auth.providers.jwt import JWTVerifier

_keycloak_realm_url = os.environ.get(
    "KEYCLOAK_REALM_URL", "http://keycloak:8080/realms/ananse"
)
_public_url = os.environ.get("MCP_PUBLIC_URL", "https://tools.ananselabs.org")

# Allow both internal docker network URL and public domain URL as valid issuers
_issuers = [
    _keycloak_realm_url.rstrip("/"),
    "https://auth.ananselabs.org/realms/ananse"
]

token_verifier = JWTVerifier(
    jwks_uri=f"{_keycloak_realm_url.rstrip('/')}/protocol/openid-connect/certs",
    issuer=_issuers,
    algorithm="RS256",
    required_scopes=["openid"],
    audience=None, # Disable strict audience verification to avoid client_id mismatches
)

auth = KeycloakAuthProvider(
    realm_url=_keycloak_realm_url,
    base_url=_public_url,
    token_verifier=token_verifier,
)



from pathlib import Path
from fastmcp.server.providers.skills import SkillsDirectoryProvider

# ── FastMCP sub-servers ──────────────────────────────────────────────────────
general = FastMCP("general")
cybops = FastMCP("cybops")

# ── Root FastMCP server ──────────────────────────────────────────────────────
mcp = FastMCP(
    "ananse-mcp",
    instructions=(
        "This server provides tools for SMS, Airtime/Data purchases, "
        "Food Orders, KYC, OTP verification, and Contacts management."
    ),
    auth=auth,
)

skills_path = Path(os.environ.get("SKILLS_DIR", "/app/skills"))
skills_path.mkdir(parents=True, exist_ok=True)
mcp.add_provider(SkillsDirectoryProvider(roots=skills_path, reload=True))

# Role-based authorization: reads realm_access.roles from the Keycloak JWT
mcp.add_middleware(KeycloakRoleMiddleware())



# Mount general tools under "general" namespace
mcp.mount(general, namespace="general")

# Mount shodan tools under "cybops" namespace
mcp.mount(cybops, namespace="cybops")

# Mount remote Kali FastMCP server under "cybops" namespace via proxy
kali_server_url = os.environ.get("KALI_SERVER_URL", "http://kali-server:8001/mcp")
kali_proxy = create_proxy(kali_server_url, name="kali-server")
mcp.mount(kali_proxy, namespace="cybops")

# Mount n8n MCP server under "n8n" namespace via proxy
n8n_server_url = os.environ.get("N8N_MCP_SERVER_URL", "https://auto.ananselabs.org/mcp-server/http")
n8n_headers = {}
n8n_api_key = os.environ.get("N8N_API_KEY")
if n8n_api_key:
    n8n_api_key = n8n_api_key.strip('\'"')
if n8n_api_key:
    n8n_headers["X-N8N-API-KEY"] = n8n_api_key
n8n_transport = SSETransport(n8n_server_url, headers=n8n_headers)
n8n_proxy = create_proxy(n8n_transport, name="n8n-server")
mcp.mount(n8n_proxy, namespace="n8n")


# ── Starlette middleware: SSE path rewrite + OpenAI challenge route ──────────
class SSESessionRewriteMiddleware:
    """Rewrites SSE session paths and serves the OpenAI Apps challenge token.

    Header normalization (x-api-key / x-role-token → Authorization: Bearer)
    has been removed — all clients must present a standard Keycloak Bearer token
    in the Authorization header.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope["method"]

            if method == "GET":
                if path == "/.well-known/openai-apps-challenge":
                    response = _challenge_endpoint(None)
                    await response(scope, receive, send)
                    return
                if path in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
                    response = _oauth_metadata(None)
                    await response(scope, receive, send)
                    return

            elif method == "POST":
                if path == "/":
                    scope["path"] = "/messages/"

        await self.app(scope, receive, send)

    def __getattr__(self, name):
        return getattr(self.app, name)


# ── http_app patch: add OpenAI Apps challenge route + SSE rewrite ──────────
_http_app_attr = inspect.getattr_static(FastMCP, "http_app")


def _challenge_endpoint(request):
    """Serves the OpenAI Apps ownership-verification token."""
    token = os.environ.get("OPENAI_APPS_CHALLENGE_TOKEN")
    if not token:
        return Response(
            "Challenge token not configured in environment",
            status_code=500,
            media_type="text/plain",
        )
    return PlainTextResponse(token)

from starlette.responses import JSONResponse

def _oauth_metadata(request):
    """Serves the OAuth authorization server metadata pointing to Keycloak."""
    return JSONResponse({
        "issuer": _keycloak_realm_url,
        "authorization_endpoint": f"{_keycloak_realm_url}/protocol/openid-connect/auth",
        "token_endpoint": f"{_keycloak_realm_url}/protocol/openid-connect/token",
        "jwks_uri": f"{_keycloak_realm_url}/protocol/openid-connect/certs",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
    })


def _with_challenge_route(app):
    """Adds the challenge route to a Starlette app if it isn't already present."""
    has_challenge = any(
        getattr(route, "path", None) == "/.well-known/openai-apps-challenge"
        for route in app.routes
    )
    if not has_challenge:
        app.routes.append(
            Route("/.well-known/openai-apps-challenge", endpoint=_challenge_endpoint, methods=["GET"])
        )
    
    has_oauth_metadata = any(
        getattr(route, "path", None) == "/.well-known/oauth-authorization-server"
        for route in app.routes
    )
    if not has_oauth_metadata:
        app.routes.append(
            Route("/.well-known/oauth-authorization-server", endpoint=_oauth_metadata, methods=["GET"])
        )
        # Also map openid-configuration just in case
        app.routes.append(
            Route("/.well-known/openid-configuration", endpoint=_oauth_metadata, methods=["GET"])
        )

    return app


if isinstance(_http_app_attr, property):
    _original_http_app = _http_app_attr.fget

    def get_custom_http_app(self):
        app = _original_http_app(self)
        app = _with_challenge_route(app)
        return SSESessionRewriteMiddleware(app)

    FastMCP.http_app = property(get_custom_http_app)

else:
    _original_http_app = _http_app_attr

    def get_custom_http_app(self, *args, **kwargs):
        app = _original_http_app(self, *args, **kwargs)
        app = _with_challenge_route(app)
        return SSESessionRewriteMiddleware(app)

    FastMCP.http_app = get_custom_http_app


# ── Diagnostic tool: inspect the current Keycloak token ─────────────────────
@mcp.tool(
    description="Returns information about the Keycloak access token for the current session.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
)
async def get_token_info() -> dict:
    token = get_access_token()

    if not token:
        return {"error": "No token provided"}

    claims = getattr(token, "claims", None) or {}
    return {
        "subject": token.subject,
        "issuer": claims.get("iss"),
        "client_id": claims.get("azp"),
        "scope": claims.get("scope"),
        "roles": claims.get("realm_access", {}).get("roles", []),
    }