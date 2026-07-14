from __future__ import annotations

import os
import logging
import jwt as pyjwt
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token, get_http_request

log = logging.getLogger(__name__)

def get_user_role() -> str:
    """
    Extract and verify the user role from the 'X-Role-Token' header.
    If the header is missing (or if request context is not available), defaults to 'user'.
    If the token is present but invalid or expired, raises a ToolError.
    """
    try:
        request = get_http_request()
    except Exception:
        # Default to 'user' if not running in HTTP request context (e.g. stdio transport)
        return "user"

    token_header = request.headers.get("x-role-token")
    if not token_header:
        return "user"

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

class RoleSecurityMiddleware(Middleware):
    """Enforce X-Role-Token role-based access control for all tools."""

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        role = get_user_role()
        if role == "admin":
            return tools
        # Filter out admin-tagged tools for non-admins
        filtered = [t for t in tools if "admin" not in (getattr(t, "tags", None) or set())]
        return filtered

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        role = get_user_role()
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
    """Block tools tagged {'admin'} unless the JWT contains role 'admin'."""

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        token = get_access_token()
        if _is_admin(token):
            return tools
        # Filter out admin-tagged tools for non-admins
        filtered = [t for t in tools if "admin" not in (getattr(t, "tags", None) or set())]
        return filtered

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        if context.fastmcp_context:
            try:
                tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
                tags = getattr(tool, "tags", None) or set()
                if "admin" in tags:
                    token = get_access_token()
                    if not _is_admin(token):
                        raise ToolError("Access denied: admin privileges required")
            except ToolError:
                raise
            except Exception as e:
                # Let execution handle missing tools
                log.warning("Error checking tags for tool %s: %s", context.message.name, e)
        return await call_next(context)

def _is_admin(token) -> bool:
    if token is None:
        return False
    
    # Check roles claim in JWT
    claims = getattr(token, "claims", None) or {}
    roles = claims.get("roles", [])
    if isinstance(roles, str):
        roles = [roles]
    return "admin" in roles

