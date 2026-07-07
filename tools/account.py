from typing import Any, Dict
from mcp.types import ToolAnnotations
from app import general as mcp
from http_client import _call_api

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def account_wallet_balance() -> Dict[str, Any]:
    """
    Check your BulkClix wallet balance.
    """
    return await _call_api("GET", "/account/balance")
