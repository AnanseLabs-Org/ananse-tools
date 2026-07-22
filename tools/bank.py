from typing import Any, Dict, Optional
from mcp.types import ToolAnnotations
from app import general as mcp
from http_client import _call_api

@mcp.tool(tags={"role:bank_admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def bank_transfer_send(
    *,
    amount: float,
    account_number: str,
    account_name: str,
    bank_code: str,
    transaction_id: str,
    narration: str = "",
    callback_url: str = ""
) -> Dict[str, Any]:
    """
    Transfer funds from your BulkClix wallet to a bank account.
    """
    data = {
        "amount": amount,
        "account_number": account_number,
        "account_name": account_name,
        "bank_code": bank_code,
        "transaction_id": transaction_id
    }
    if narration:
        data["narration"] = narration
    if callback_url:
        data["callback_url"] = callback_url
    return await _call_api("POST", "/payment-api/bank-transfer", json_data=data)

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def bank_list() -> Dict[str, Any]:
    """
    List all supported banks and their bank codes.
    """
    return await _call_api("GET", "/payment-api/banks")
