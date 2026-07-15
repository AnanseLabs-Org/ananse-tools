from mcp.types import ToolAnnotations
from typing import Any, Dict, Optional
from app import general as mcp
from http_client import _call_api
from auth import _get_payment_bearer_token
from payments.helpers import _fetch_payment_history, _find_payment_history_match, _is_not_found_response, _payment_status_from_record

@mcp.tool(tags={"role:payments_user"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def momo_collect(
    *,
    amount: float,
    phone_number: str,
    network: str,
    transaction_id: str,
    callback_url: Optional[str] = None,
    reference: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initiate a Mobile Money collection — prompts the customer to approve payment.
    :param amount: Amount to collect in GHS.
    :param phone_number: Customer's MoMo phone number.
    :param network: Customer's mobile network ('MTN', 'TELECEL', 'AIRTELTIGO').
    :param transaction_id: Unique transaction reference.
    :param callback_url: Webhook URL to send payment updates to.
    :param reference: Label/reference displayed on customer's approval screen.
    """
    data = {
        "amount": amount,
        "phone_number": phone_number,
        "network": network,
        "transaction_id": transaction_id
    }
    if callback_url:
        data["callback_url"] = callback_url
    if reference:
        data["reference"] = reference
    return await _call_api( "POST", "/payment-api/momopay", json_data=data)

@mcp.tool(
    description="Check the status of a Mobile Money collection or transaction. :param transaction_id: The transaction ID returned during collection. :param payment_id: Optional payment record ID if you already have it.",
    tags={"role:payments_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def momo_check_status(
    *,
    transaction_id: str,
    payment_id: str | None = None
) -> Dict[str, Any]:
    """
    Check the status of a Mobile Money collection or transaction.
    :param transaction_id: The transaction ID returned during collection.
    :param payment_id: Optional payment record ID if you already have it.
    """
    resolved_payment_id = payment_id
    if not resolved_payment_id:
        history = await _fetch_payment_history(search=transaction_id, page_size=25)
        matched_record = _find_payment_history_match(history, [transaction_id])
        if matched_record:
            resolved_payment_id = matched_record.get("id") if isinstance(matched_record.get("id"), str) else None

    lookup_id = resolved_payment_id or transaction_id
    status_response = await _call_api("GET", f"/pay/checkstatus/{lookup_id}")
    if _is_not_found_response(status_response):
        history = await _fetch_payment_history(search=transaction_id, page_size=25)
        matched_record = _find_payment_history_match(history, [transaction_id, lookup_id])
        if matched_record:
            return {
                "status": _payment_status_from_record(matched_record) or "unknown",
                "record": matched_record,
                "source": "payment_history",
            }
    return status_response


@mcp.tool(
    description="Verify a payment OTP after the customer reads the code from their phone and sends it in chat. CRITICAL: This is ONLY for validating payment-related transactions. The request_id MUST be the one returned in the response of a payment/purchase initiation tool (e.g., airtime_purchase, data_purchase, or momo_collect), NOT from otp_send_sms. Providing a standard SMS OTP request ID will result in a 404 Error. :param code: OTP code entered by the customer from their phone. :param request_id: Request ID returned from the payment/purchase initiation response. :param phone_number: The phone number used for the payment transaction.",
    tags={"role:payments_user"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
)
async def pay_verify_otp(
    *,
    code: str,
    request_id: str,
    phone_number: str
) -> Dict[str, Any]:
    """
    Verify a payment OTP after the customer reads the code from their phone and sends it in chat.
    
    CRITICAL: This is ONLY for validating payment-related transactions. The `request_id` MUST be the one returned in the response of a payment/purchase initiation tool (e.g., `airtime_purchase`, `data_purchase`, or `momo_collect`), NOT from `otp_send_sms`. Providing a standard SMS OTP request ID will result in a 404 Error.
    
    :param code: OTP code entered by the customer from their phone.
    :param request_id: Request ID returned from the payment/purchase initiation response.
    :param phone_number: The phone number used for the payment transaction.
    """
    bearer_token = _get_payment_bearer_token()
    extra_headers = {}
    if bearer_token:
        extra_headers["Authorization"] = f"Bearer {bearer_token}"

    return await _call_api(
        "POST",
        "/pay/verify-otp",
        json_data={
            "code": code,
            "requestId": request_id,
            "phoneNumber": phone_number,
        },
        extra_headers=extra_headers or None,
    )


@mcp.tool(tags={"role:payments_admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def momo_disburse(
    *,
    amount: float,
    phone_number: str,
    network: str,
    transaction_id: str,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send/disburse money from your BulkClix wallet balance to a MoMo phone number.
    :param amount: Amount to disburse in GHS.
    :param phone_number: Recipient's MoMo number.
    :param network: Network of the recipient ('MTN', 'TELECEL', 'AIRTELTIGO').
    :param transaction_id: Unique transaction reference.
    :param callback_url: Webhook URL to send transaction state changes to.
    """
    data = {
        "amount": amount,
        "phone_number": phone_number,
        "network": network,
        "transaction_id": transaction_id
    }
    if callback_url:
        data["callback_url"] = callback_url
    return await _call_api( "POST", "/payment-api/disburse", json_data=data)
