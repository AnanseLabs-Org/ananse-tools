from typing import Any, Dict
from mcp.types import ToolAnnotations
from app import cybops as mcp
from shodan import APIError
from tools.cybops.utils import _get_client

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_search(
    *,
    query: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Search the Shodan database using the same query syntax as the website.
    :param query: Shodan search query (e.g. "apache", "port:22").
    :param limit: Maximum number of search results to return (default 50).
    """
    try:
        client = _get_client()
        results = client.search(query, limit=limit)
        return dict(results)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_count(
    *,
    query: str
) -> Dict[str, Any]:
    """
    Get the total number of results that match a search query without returning the hosts (saves query credits).
    :param query: Shodan search query (e.g. "apache", "port:22").
    """
    try:
        client = _get_client()
        results = client.count(query)
        return dict(results)
    except APIError as e:
        return {"error": str(e)}

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def shodan_search_tokens(
    *,
    query: str
) -> Dict[str, Any]:
    """
    Parse a search query into tokens to check syntax and see how Shodan filters it.
    :param query: Shodan query string.
    """
    try:
        client = _get_client()
        results = client.search_tokens(query)
        return dict(results)
    except APIError as e:
        return {"error": str(e)}
