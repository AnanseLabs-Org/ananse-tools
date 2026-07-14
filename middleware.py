from __future__ import annotations

import os
import logging
import jwt as pyjwt
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token, get_http_request

log = logging.getLogger(__name__)

def get_user_role() -> str | None:
    """
    Extract and verify the user role from the 'X-Role-Token' header.
    If the header is missing (or if request context is not available), returns None.
    If the token is present but invalid or expired, raises a ToolError.
    """
    try:
        request = get_http_request()
    except Exception:
        # Default to None if not running in HTTP request context (e.g. stdio transport)
        return None

    token_header = request.headers.get("x-role-token")
    if not token_header:
        return None

    secret = os.environ.get("MCP_ROLE_TOKEN_SECRET")
    if not secret:
        log.warning("x-role-token header present, but MCP_ROLE_TOKEN_SECRET is not set.")
        raise ToolError("Security configuration error: MCP_ROLE_TOKEN_SECRET not set")

    try:
        token = token_header
        if token.lower().startswith("bearer "):
            token = token[7:]

        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        role = payload.get("role")
        if not role:
            roles = payload.get("roles")
            if roles:
                if isinstance(roles, str):
                    role = roles
                elif isinstance(roles, list) and len(roles) > 0:
                    role = roles[0]

        if not role:
            raise ToolError("Invalid token: no role/roles claim found")

        role = role.lower()
        if role not in ("user", "admin"):
            raise ToolError(f"Invalid token: unknown role '{role}'")

        return role

    except pyjwt.ExpiredSignatureError:
        raise ToolError("Token signature has expired")
    except pyjwt.InvalidTokenError as e:
        raise ToolError(f"Invalid security token: {str(e)}")

def get_resolved_role() -> str:
    """
    Resolves the caller's role to 'admin' or 'user' by checking both
    the 'X-Role-Token' header and the OAuth token claims (OR logic).
    If no token is provided by either method, raises a ToolError (no access).
    """
    # 1. Check X-Role-Token header
    role = get_user_role()
    if role == "admin":
        return "admin"
    elif role == "user":
        return "user"

    # 2. Check OAuth access token claims
    try:
        token = get_access_token()
        if token is not None:
            claims = getattr(token, "claims", None) or {}
            roles = claims.get("roles", [])
            if isinstance(roles, str):
                roles = [roles]
            if "admin" in roles:
                return "admin"
            return "user"
    except Exception:
        pass

    # No token provided by either method
    raise ToolError("Authentication required: no token provided")

class RoleSecurityMiddleware(Middleware):
    """Enforce role-based access control checking both X-Role-Token and OAuth claims."""

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        role = get_resolved_role()
        if role == "admin":
            return tools
        # Filter out admin-tagged tools for non-admins
        filtered = [t for t in tools if "admin" not in (getattr(t, "tags", None) or set())]
        return filtered

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        role = get_resolved_role()
        if role != "admin":
            if context.fastmcp_context:
                try:
                    tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
                    tags = getattr(tool, "tags", None) or set()
                    if "admin" in tags:
                        raise ToolError("Access denied: admin privileges required")
                except ToolError:
                    raise
                except Exception as e:
                    # Let execution handle missing tools
                    log.warning("Error checking tags for tool %s: %s", context.message.name, e)
        return await call_next(context)

class AdminTagMiddleware(Middleware):
    """Legacy middleware: role checking is now handled by RoleSecurityMiddleware."""
    async def on_list_tools(self, context, call_next):
        return await call_next(context)
    async def on_call_tool(self, context, call_next):
        return await call_next(context)


