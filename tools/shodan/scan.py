from typing import Any, Dict, List
from mcp.types import ToolAnnotations
from app import mcp
from shodan import APIError
from tools.shodan.utils import _get_client

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def shodan_scan(
    *,
    ips: List[str],
    force: bool = False
) -> Dict[str, Any]:
    """
    Request Shodan to scan a network range or list of IPs.
    :param ips: A list of IPs or network ranges in CIDR format.
    :param force: Whether to force a scan even if scanned recently.
    """
    try:
        client = _get_client()
        result = client.scan(ips, force=force)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_scan_status(
    *,
    scan_id: str
) -> Dict[str, Any]:
    """
    Get the status of a previously requested scan.
    :param scan_id: The unique scan ID.
    """
    try:
        client = _get_client()
        result = client.scan_status(scan_id)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_scans(
    *,
    page: int = 1
) -> Dict[str, Any]:
    """
    List all previously requested scans.
    :param page: The page number to retrieve.
    """
    try:
        client = _get_client()
        result = client.scans(page=page)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}
