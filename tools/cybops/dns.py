from typing import Any, Dict, List
from mcp.types import ToolAnnotations
from app import cybops as mcp
from shodan import APIError
from tools.cybops.utils import _get_client

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_dns_resolve(
    *,
    hostnames: List[str]
) -> Dict[str, Any]:
    """
    Resolve a list of hostnames to their corresponding IP addresses.
    :param hostnames: A list of domain names/hostnames to resolve.
    """
    try:
        client = _get_client()
        result = client._request('/dns/resolve', {'hostnames': ','.join(hostnames)})
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_dns_reverse(
    *,
    ips: List[str]
) -> Dict[str, Any]:
    """
    Look up the hostnames associated with a list of IP addresses.
    :param ips: A list of IP addresses to look up.
    """
    try:
        client = _get_client()
        result = client._request('/dns/reverse', {'ips': ','.join(ips)})
        return dict(result)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_domain_info(
    *,
    domain: str,
    history: bool = False,
    type: str = None
) -> Dict[str, Any]:
    """
    Grab the DNS information/records for a domain, optionally with history and specific record type.
    :param domain: The domain name to query (e.g. "google.com").
    :param history: Whether or not to include historical DNS data.
    :param type: Only return DNS records of this type (e.g. "A", "MX").
    """
    try:
        client = _get_client()
        result = client.dns.domain_info(domain, history=history, type=type)
        return dict(result)
    except APIError as e:
        return {"error": str(e)}
