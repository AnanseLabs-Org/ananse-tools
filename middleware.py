"""
Keycloak role-based authorization middleware for FastMCP.

Reads ``realm_access.roles`` from the validated Keycloak JWT and:

- ``on_list_tools``  – filters out tools whose required role the caller lacks
- ``on_call_tool``   – blocks execution with ToolError if the caller lacks the role

Role requirements are declared on tools via a ``role:`` tag, e.g.::

    @mcp.tool(tags={"role:sms_user"})
    async def sms_send(...): ...

The special tag ``role:admin`` requires the ``admin`` realm role.
If a tool carries **no** ``role:*`` tag it is accessible to any authenticated user.
Callers who hold the ``admin`` realm role bypass all per-tool role checks.
"""
from __future__ import annotations

import logging
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_access_token
from fastmcp.exceptions import ToolError

log = logging.getLogger(__name__)

ROLE_TAG_PREFIX = "role:"


def _get_caller_roles() -> set[str]:
    """Extract Keycloak realm roles from the current request's access token.

    Returns an empty set when no token is present (unauthenticated request).
    FastMCP's KeycloakAuthProvider will already have rejected the request before
    we reach this point if authentication is required, so an empty set here
    only applies to optional/public paths.
    """
    try:
        token = get_access_token()
        if token is None:
            return set()
        claims = getattr(token, "claims", None) or {}
        roles = claims.get("realm_access", {}).get("roles", [])
        return set(roles)
    except Exception as exc:
        log.warning("Could not extract Keycloak realm roles: %s", exc)
        return set()


def _required_role(tool) -> str | None:
    """Return the required role from a tool's ``role:*`` tag, or ``None`` if unrestricted."""
    tags = getattr(tool, "tags", None) or set()
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(ROLE_TAG_PREFIX):
            return tag[len(ROLE_TAG_PREFIX):]
    return None


def _caller_has_access(tool, caller_roles: set[str]) -> bool:
    """Return True if the caller's roles satisfy the tool's role requirement."""
    required = _required_role(tool)
    if required is None:
        return True  # No role restriction — open to any authenticated user
    # Callers with the 'admin' realm role always pass
    return required in caller_roles or "admin" in caller_roles


class KeycloakRoleMiddleware(Middleware):
    """Enforce role-based access control using Keycloak ``realm_access.roles`` claims.

    Listing operations (``tools/list``) silently filter out inaccessible tools.
    Execution operations (``tools/call``) raise a ``ToolError`` if access is denied.
    """

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        caller_roles = _get_caller_roles()
        if "admin" in caller_roles:
            return tools  # Admins see everything
        return [t for t in tools if _caller_has_access(t, caller_roles)]

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        caller_roles = _get_caller_roles()
        if "admin" not in caller_roles and context.fastmcp_context:
            try:
                tool = await context.fastmcp_context.fastmcp.get_tool(
                    context.message.name
                )
                if not _caller_has_access(tool, caller_roles):
                    required = _required_role(tool)
                    raise ToolError(
                        f"Access denied: role '{required}' required. "
                        f"Your roles: {sorted(caller_roles) or ['none']}"
                    )
            except ToolError:
                raise
            except Exception as exc:
                log.warning(
                    "Role check error for tool %s: %s", context.message.name, exc
                )
        return await call_next(context)
