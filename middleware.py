from __future__ import annotations

import logging
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

log = logging.getLogger(__name__)

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
