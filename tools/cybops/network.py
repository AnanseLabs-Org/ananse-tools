from typing import Any, Dict
from mcp.types import ToolAnnotations
from app import cybops as mcp
from shodan import APIError
from tools.cybops.utils import _get_client

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def shodan_create_alert(
    *,
    name: str,
    ip: str,
    expires: int = 0
) -> Dict[str, Any]:
    """
    Create a network alert/private firehose for the specified IP range(s).
    :param name: Name of the alert.
    :param ip: Network range(s) to monitor (e.g. CIDR notation).
    :param expires: Expiration time in seconds (0 for never).
    """
    try:
        client = _get_client()
        result = client.create_alert(name, ip, expires=expires)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_alerts(
    *,
    aid: str = None,
    include_expired: bool = True
) -> Dict[str, Any] | list:
    """
    List all of the active network alerts or retrieve a specific alert's info.
    :param aid: Alert ID to fetch info for (None to list all alerts).
    :param include_expired: Whether to include expired alerts in listings.
    """
    try:
        client = _get_client()
        result = client.alerts(aid=aid, include_expired=include_expired)
        if isinstance(result, list):
            return result
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def shodan_delete_alert(
    *,
    aid: str
) -> Dict[str, Any]:
    """
    Delete a network alert.
    :param aid: The Alert ID to delete.
    """
    try:
        client = _get_client()
        result = client.delete_alert(aid)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}
