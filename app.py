import os
from typing import Any, Mapping, Sequence

import jwt as pyjwt
import fastmcp
import inspect
from fastmcp import FastMCP
from fastmcp.server import create_proxy
from fastmcp.client.transports.sse import SSETransport
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.auth0 import Auth0Provider
from fastmcp.server.dependencies import get_access_token
from mcp.types import ToolAnnotations
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from db import _get_db
from middleware import AdminTagMiddleware, RoleSecurityMiddleware
from fastmcp.server.transforms.search import BM25SearchTransform

# ── Global fastmcp settings ─────────────────────────────────────────────────
fastmcp.settings.sse_path = "/"
fastmcp.settings.message_path = "/messages/"


# ── Mongo-backed key/value store (used for Auth0 client storage) ───────────
class MongoKeyValue:
    def __init__(self, default_collection: str = "oauth_store"):
        self.default_collection = default_collection

    def _get_collection(self, name: str | None):
        col_name = name or self.default_collection
        db = _get_db()
        if db is None:
            raise RuntimeError("Database connection not initialized")
        return db[col_name]

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        col = self._get_collection(collection)
        doc = await col.find_one({"_id": key})
        if doc:
            val = dict(doc)
            val.pop("_id", None)
            return val
        return None

    async def ttl(self, key: str, *, collection: str | None = None) -> tuple[dict[str, Any] | None, float | None]:
        val = await self.get(key, collection=collection)
        return val, None

    async def put(self, key: str, value: Mapping[str, Any], *, collection: str | None = None, ttl: Any = None) -> None:
        col = self._get_collection(collection)
        data = dict(value)
        data["_id"] = key
        await col.replace_one({"_id": key}, data, upsert=True)

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        col = self._get_collection(collection)
        result = await col.delete_one({"_id": key})
        return result.deleted_count > 0

    async def get_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[dict[str, Any] | None]:
        col = self._get_collection(collection)
        cursor = col.find({"_id": {"$in": list(keys)}})
        docs = await cursor.to_list(length=len(keys))
        docs_map = {doc["_id"]: doc for doc in docs}
        return [
            ({**doc, **{}} if (doc := docs_map.get(k)) is None else {k2: v for k2, v in doc.items() if k2 != "_id"})
            for k in keys
        ]

    async def ttl_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[tuple[dict[str, Any] | None, float | None]]:
        vals = await self.get_many(keys, collection=collection)
        return [(val, None) for val in vals]

    async def put_many(self, keys: Sequence[str], values: Sequence[Mapping[str, Any]], *, collection: str | None = None, ttl: Any = None) -> None:
        from pymongo import ReplaceOne  # deferred: only needed for bulk writes

        col = self._get_collection(collection)
        operations = [
            ReplaceOne({"_id": k}, {**v, "_id": k}, upsert=True)
            for k, v in zip(keys, values)
        ]
        if operations:
            await col.bulk_write(operations)

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        col = self._get_collection(collection)
        result = await col.delete_many({"_id": {"$in": list(keys)}})
        return result.deleted_count


# ── Auth0 provider (optional, enabled via env var) ──────────────────────────
def _build_auth_provider() -> Auth0Provider | None:
    """Constructs the Auth0Provider with a custom token-verification path
    that supports static/legacy tokens alongside normal Auth0 tokens."""
    if os.environ.get("MCP_ENABLE_AUTH0", "false").lower() != "true":
        return None

    auth0_domain = os.environ.get("AUTH0_DOMAIN")
    auth0_client_id = os.environ.get("AUTH0_CLIENT_ID")
    auth0_client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
    auth0_audience = os.environ.get("AUTH0_AUDIENCE")
    public_url = os.environ.get("MCP_PUBLIC_URL")

    if not all([auth0_domain, auth0_client_id, auth0_client_secret, auth0_audience, public_url]):
        raise RuntimeError("Missing required Auth0 or public URL configurations in environment")

    provider = Auth0Provider(
        config_url=f"https://{auth0_domain}/.well-known/openid-configuration",
        client_id=auth0_client_id,
        client_secret=auth0_client_secret,
        audience=auth0_audience,
        base_url=public_url,
        client_storage=MongoKeyValue(),
    )

    original_verify = provider.verify_token

    async def custom_verify_token(token: str):
        clean_token = token[7:] if token.lower().startswith("bearer ") else token

        # 1. Try a role token (signed with MCP_ROLE_TOKEN_SECRET)
        role_secret = os.environ.get("MCP_ROLE_TOKEN_SECRET")
        if role_secret:
            try:
                payload = pyjwt.decode(clean_token, role_secret, algorithms=["HS256"])
                role = payload.get("role", "user")
                return AccessToken(
                    token=token,
                    subject="m2m-user",
                    client_id="m2m",
                    scopes=["openid"],
                    claims={"scope": "openid", "roles": [role]},
                )
            except pyjwt.PyJWTError:
                pass

        # 3. Fall back to normal Auth0 verification
        return await original_verify(token)

    provider.verify_token = custom_verify_token
    return provider


auth_provider = _build_auth_provider()


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
    auth=auth_provider,
)

skills_path = Path(os.environ.get("SKILLS_DIR", "/app/skills"))
skills_path.mkdir(parents=True, exist_ok=True)
mcp.add_provider(SkillsDirectoryProvider(roots=skills_path, reload=True))

# Enforce {'admin'} tags using JWT claims
mcp.add_middleware(AdminTagMiddleware())
mcp.add_middleware(RoleSecurityMiddleware())

# Compress tool list and require search/call-tool for hidden tools
mcp.add_transform(BM25SearchTransform(always_visible=["search", "get_token_info"]))

# Mount general tools under "general" namespace
mcp.mount(general, namespace="general")

# Mount shodan tools under "cybops" namespace
mcp.mount(cybops, namespace="cybops")

# Mount remote Kali FastMCP server under "cybops" namespace via proxy
kali_server_url = os.environ.get("KALI_SERVER_URL", "http://kali-server:8001/mcp")
# Configure proxy client options if needed, but since it is direct HTTP connection on tools-network:
# We must disable DNS rebinding on the backend (kali-server) so that proxy calls from app.py do not fail with 421.
# Since we are mounting it, we want the proxy calls to be accepted.
kali_proxy = create_proxy(kali_server_url, name="kali-server")
mcp.mount(kali_proxy, namespace="cybops")

# Mount n8n MCP server under "n8n" namespace via proxy
n8n_server_url = os.environ.get("N8N_MCP_SERVER_URL", "https://auto.ananselabs.org/mcp-server/http")
n8n_headers = {}
n8n_api_key = os.environ.get("N8N_API_KEY")
if n8n_api_key:
    n8n_headers["X-N8N-API-KEY"] = n8n_api_key
n8n_transport = SSETransport(n8n_server_url, headers=n8n_headers)
n8n_proxy = create_proxy(n8n_transport, name="n8n-server")
mcp.mount(n8n_proxy, namespace="n8n")


# ── Starlette middleware: header normalization + SSE session path rewrite ──
class SSESessionRewriteMiddleware:
    """Normalizes auth headers and rewrites a couple of well-known paths so
    that SSE clients and OAuth discovery both hit the right routes."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope["method"]
            headers = dict(scope["headers"])

            # Convert x-role-token case-insensitively to Authorization: Bearer
            role_token = None
            for k, v in headers.items():
                if k.lower() == b"x-role-token":
                    role_token = v
                    break
            if role_token:
                headers[b"authorization"] = b"Bearer " + role_token

            # Convert x-api-key to Authorization: Bearer
            x_api_key = headers.get(b"x-api-key")
            if x_api_key:
                headers[b"authorization"] = b"Bearer " + x_api_key

            # Ensure Authorization header starts with Bearer
            auth_header = headers.get(b"authorization")
            if auth_header and not auth_header.lower().startswith(b"bearer "):
                headers[b"authorization"] = b"Bearer " + auth_header

            scope["headers"] = list(headers.items())

            if method == "GET":
                # Normalize openid-configuration to oauth-authorization-server
                if ".well-known/openid-configuration" in path:
                    scope["path"] = "/.well-known/oauth-authorization-server"

            elif method == "POST":
                if path == "/":
                    scope["path"] = "/messages/"
                if "messages" in path:
                    headers_dict = {
                        k.decode("utf-8", errors="ignore"): v.decode("utf-8", errors="ignore")
                        for k, v in scope.get("headers", [])
                    }
                    print(
                        f"DEBUG_POST: path={path} "
                        f"query_string={scope.get('query_string', b'').decode('utf-8')} "
                        f"headers={headers_dict}",
                        flush=True,
                    )

        await self.app(scope, receive, send)

    def __getattr__(self, name):
        return getattr(self.app, name)


# ── http_app patch: add OpenAI Apps challenge route + SSE rewrite ──────────
# `http_app` is a property in some fastmcp versions and a plain method in
# others — detect which one we have and wrap accordingly.
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
    return app


if isinstance(_http_app_attr, property):
    # Property descriptor case
    _original_http_app = _http_app_attr.fget

    def get_custom_http_app(self):
        app = _original_http_app(self)
        app = _with_challenge_route(app)
        return SSESessionRewriteMiddleware(app)

    FastMCP.http_app = property(get_custom_http_app)

else:
    # Plain method case (this is what your installed fastmcp version uses)
    _original_http_app = _http_app_attr

    def get_custom_http_app(self, *args, **kwargs):
        app = _original_http_app(self, *args, **kwargs)
        app = _with_challenge_route(app)
        return SSESessionRewriteMiddleware(app)

    FastMCP.http_app = get_custom_http_app


# ── Diagnostic tool: inspect the current auth token ─────────────────────────
@mcp.tool(
    description="Returns information about the Auth0 token.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
)
async def get_token_info() -> dict:
    token = get_access_token()

    if not token:
        return {"error": "No token provided"}

    return {
        "issuer": token.claims.get("iss") if token.claims else None,
        "audience": token.claims.get("aud") if token.claims else None,
        "scope": token.claims.get("scope") if token.claims else None,
        "subject": token.subject,
        "client_id": token.client_id,
    }