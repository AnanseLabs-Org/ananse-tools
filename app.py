import os
import config
import fastmcp
from fastmcp import FastMCP
from fastmcp.server.auth.providers.auth0 import Auth0Provider

# Configure settings globally
fastmcp.settings.sse_path = "/"
fastmcp.settings.message_path = "/messages/"

from typing import Any, Mapping, Sequence
from db import _get_db

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
        results = []
        for k in keys:
            doc = docs_map.get(k)
            if doc:
                val = dict(doc)
                val.pop("_id", None)
                results.append(val)
            else:
                results.append(None)
        return results

    async def ttl_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[tuple[dict[str, Any] | None, float | None]]:
        vals = await self.get_many(keys, collection=collection)
        return [(val, None) for val in vals]

    async def put_many(self, keys: Sequence[str], values: Sequence[Mapping[str, Any]], *, collection: str | None = None, ttl: Any = None) -> None:
        col = self._get_collection(collection)
        from pymongo import ReplaceOne
        operations = []
        for k, v in zip(keys, values):
            data = dict(v)
            data["_id"] = k
            operations.append(ReplaceOne({"_id": k}, data, upsert=True))
        if operations:
            await col.bulk_write(operations)

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        col = self._get_collection(collection)
        result = await col.delete_many({"_id": {"$in": list(keys)}})
        return result.deleted_count

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
        client_storage=MongoKeyValue(),
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

    def __getattr__(self, name):
        return getattr(self.app, name)

original_http_app = mcp.http_app
def custom_http_app(*args, **kwargs):
    # Enforce transport="sse" if not specified, since we run on SSE
    if "transport" not in kwargs:
        kwargs["transport"] = "sse"
    app = original_http_app(*args, **kwargs)
    
    # Add openai-apps-challenge verification endpoint
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def challenge_endpoint(request):
        token = os.environ.get("OPENAI_APPS_CHALLENGE_TOKEN")
        if not token:
            from starlette.responses import Response
            return Response("Challenge token not configured in environment", status_code=500, media_type="text/plain")
        return PlainTextResponse(token)

    app.routes.append(
        Route("/.well-known/openai-apps-challenge", endpoint=challenge_endpoint, methods=["GET"])
    )
    
    return SSESessionRewriteMiddleware(app)
mcp.http_app = custom_http_app

# Add a protected tool to test authentication
from mcp.types import ToolAnnotations

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
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
