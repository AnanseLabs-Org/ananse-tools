from typing import Any, Dict, List
from mcp.types import ToolAnnotations
from app import mcp
from shodan import APIError
from tools.shodan.utils import _get_client

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_host(
    *,
    ip: str
) -> Dict[str, Any]:
    """
    Retrieve all information Shodan has gathered for a specific IP address.
    :param ip: The IP address to query (e.g. "8.8.8.8").
    """
    try:
        client = _get_client()
        info = client.host(ip)
        return dict(info)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_info() -> Dict[str, Any]:
    """
    Retrieve information about the API plan, credits, and usage limits of the current Shodan account.
    """
    try:
        client = _get_client()
        info = client.info()
        return dict(info)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_honeyscore(
    *,
    ip: str
) -> Dict[str, Any]:
    """
    Calculate the probability that an IP address is a honeypot (0.0 to 1.0).
    :param ip: The IP address to check.
    """
    try:
        client = _get_client()
        score = client.labs.honeyscore(ip)
        return {"ip": ip, "honeyscore": score}
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_ports() -> List[int]:
    """
    Get a list of ports that Shodan crawls.
    """
    try:
        client = _get_client()
        ports = client.ports()
        return list(ports)
    except APIError as e:
        # FastMCP tools returning list is fine, let's keep it safe
        return []

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_protocols() -> Dict[str, str]:
    """
    Get a list of protocols that Shodan crawls and parses.
    """
    try:
        client = _get_client()
        protocols = client.protocols()
        return dict(protocols)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_services() -> Dict[str, str]:
    """
    Get a list of services that Shodan parses.
    """
    try:
        client = _get_client()
        services = client.services()
        return dict(services)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_myip() -> Dict[str, str]:
    """
    Get your current IP address as seen from the Internet.
    """
    try:
        client = _get_client()
        ip = client.tools.myip()
        return {"ip": ip}
    except APIError as e:
        return {"error": str(e)}
