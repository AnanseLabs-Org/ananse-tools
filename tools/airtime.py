from mcp.types import ToolAnnotations
from typing import Any, Dict
from app import mcp
from decorators import internal_tool
from http_client import _call_api

@mcp.tool(
    description="Get supported networks for airtime top-up.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def airtime_get_networks() -> Dict[str, Any]:
    """
    Get supported networks for airtime top-up.
    """
    return await _call_api( "GET", "/airtime-api/networks")

@mcp.tool(
    description="Start an airtime purchase using the BulkClix purchase route. :param destination: Recipient phone number receiving the airtime. :param phone_number: MoMo phone number being charged for payment. :param network: Payer network code (e.g., 'MTN', 'VDF', 'ATL'). :param amount: Airtime purchase amount in GHS. :param network_id: Network UUID from airtime_get_networks. :param payment_type: Payment type (usually 'momo').",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def airtime_purchase(
    *,
    destination: str,
    phone_number: str,
    network: str,
    amount: float,
    network_id: str,
    payment_type: str = "momo",
    transaction_id: str | None = None,
    await_payment: bool = True,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
    callback_url: str | None = None,
    reference: str | None = None,
) -> Dict[str, Any]:
    """
    Start an airtime purchase using the BulkClix purchase route.
    :param destination: Recipient phone number receiving the airtime.
    :param phone_number: MoMo phone number being charged for payment.
    :param network: Payer network code (e.g., 'MTN', 'VDF', 'ATL').
    :param amount: Airtime purchase amount in GHS.
    :param network_id: Network UUID from airtime_get_networks.
    :param payment_type: Payment type (usually 'momo').
    """
    payload = {
        "destination": destination,
        "phoneNumber": phone_number,
        "network": network,
        "amount": amount,
        "network_id": network_id,
        "type": payment_type,
    }
    if transaction_id:
        payload["transaction_id"] = transaction_id
    if callback_url:
        payload["callback_url"] = callback_url
    if reference:
        payload["reference"] = reference
    return await _call_api(
        "POST",
        "/airtime-api/buy",
        json_data=payload,
    )

@internal_tool(read_only=False, destructive=False, open_world=True)
async def airtime_send(
    *,
    phone_number: str,
    network_id: str,
    amount: float,
    transaction_id: str
) -> Dict[str, Any]:
    """
    Send airtime directly to a recipient number using your BulkClix wallet balance.
    :param phone_number: Recipient phone number.
    :param network_id: Network UUID from airtime_get_networks.
    :param amount: Airtime amount in GHS.
    :param transaction_id: Your unique transaction reference.
    """
    return await _call_api(
        "POST",
        "/airtime-api/sendAirtime",
        json_data={
            "phone_number": phone_number,
            "network_id": network_id,
            "amount": amount,
            "transaction_id": transaction_id
        }
    )
