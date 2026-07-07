from typing import Any, Dict
from mcp.types import ToolAnnotations
from app import general as mcp
from http_client import _call_api

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def kyc_msisdn_name_query(
    *,
    phone_number: str
) -> Dict[str, Any]:
    """
    Look up the registered owner's name for a phone number.
    :param phone_number: Target phone number (e.g. '0541008285').
    """
    return await _call_api("GET", "/kyc-api/msisdNameQuery", params={"phone_number": phone_number})
