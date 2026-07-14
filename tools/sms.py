from typing import Any, Dict, List
from mcp.types import ToolAnnotations
from app import general as mcp
from http_client import _call_api

def _extract_sender_records(payload: Any) -> list[Any]:
    """Return sender ID records from a BulkClix sender list response."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items", "senderIds", "sender_ids", "senders"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    return []

def _extract_sender_id(record: Any) -> str | None:
    """Return the sender ID name string from a sender ID record."""
    if isinstance(record, str):
        return record
    if isinstance(record, dict):
        for key in ("name", "sender_id", "senderId", "sender"):
            val = record.get(key)
            if isinstance(val, str):
                return val
    return None

async def _get_default_sender_id() -> str:
    """Fetch the first available sender ID from the BulkClix account."""
    response = await _call_api("GET", "/sms-api/senderIds")
    for record in _extract_sender_records(response):
        sender_id = _extract_sender_id(record)
        if sender_id:
            return sender_id
    raise RuntimeError("No sender ID is configured on the BulkClix account.")


@mcp.tool(tags={"role:sms_user"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def sms_send(
    *,
    message: str,
    recipients: List[str]
) -> Dict[str, Any]:
    """
    Send an SMS message to one or many phone numbers (bulk SMS).
    :param message: The text message content to send.
    :param recipients: List of recipient phone numbers (e.g. ["0541008285", "0265951172"]).
    """
    sender_id = await _get_default_sender_id()
    return await _call_api( 
        "POST", 
        "/sms-api/send", 
        json_data={
            "sender_id": sender_id,
            "message": message,
            "recipients": recipients
        }
    )

@mcp.tool(tags={"role:sms_user"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def sms_get_campaign_report(
    *,
    campaign_id: str
) -> Dict[str, Any]:
    """
    Get the delivery report for a specific SMS campaign.
    :param campaign_id: The campaign ID returned from sms_send.
    """
    return await _call_api("GET", f"/sms-api/campaignMessages/{campaign_id}")

@mcp.tool(tags={"role:sms_user"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def senderid_list() -> Dict[str, Any]:
    """
    List all SMS Sender IDs registered on your BulkClix account along with their status.
    """
    return await _call_api("GET", "/sms-api/senderIds")

@mcp.tool(tags={"role:sms_user"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def senderid_request(
    *,
    name: str,
    desc: str
) -> Dict[str, Any]:
    """
    Request a new Sender ID for your BulkClix account.
    :param name: The Sender ID name (max 11 alphanumeric characters).
    :param desc: Purpose/description of what this Sender ID will be used for.
    """
    return await _call_api(
        "POST",
        "/sms-api/requestSenderId",
        json_data={"name": name, "desc": desc}
    )
