#!/usr/bin/env python3
"""
BulkClix MCP Server (Python / FastMCP edition)
==============================================
An AI agent portal for interacting with the BulkClix platform.
Supports: SMS, Airtime, Data Bundles, Mobile Money, Bank Transfers, OTP, KYC, Contacts.

Authentication: The server reads BULKCLIX_API_KEY from the environment.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from mcp.server.fastmcp import FastMCP

from mcp.server.transport_security import TransportSecuritySettings


def _load_env_file(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file()

# Initialize FastMCP Server
mcp = FastMCP(
    "bulkclix-mcp",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8000")),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

BASE_URL = "https://api.bulkclix.com/api/v1"
ENABLE_INTERNAL_TOOLS = os.environ.get("BULKCLIX_ENABLE_INTERNAL_TOOLS", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

STATIC_VENDORS_LIST = [
    {
        "vendor_id": "234490c6-09e1-4125-b9cd-506d64eb2c50",
        "name": "Horlap",
        "categories": ["restaurant", "food_delivery", "food"],  # added alias
        "order_types": ["inhouse"],
        "menu_url": "https://api.horlap.com/api/menu/",
        "order_url": "https://api.horlap.com/api/orders/create-and-initiate-payment/",
        "payment_methods": ["momo"],
    }
]

_INTERNAL_ONLY_FIELDS = {"menu_url", "order_url"}


def _lookup_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    """
    Internal lookup returning the FULL vendor record, including API endpoints.
    Use this from other tools — NOT get_verified_vendors(), which strips
    menu_url/order_url before returning to the model.
    """
    return next((v for v in STATIC_VENDORS_LIST if v["vendor_id"] == vendor_id), None)


def _public_vendor_view(vendor: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal-only fields (API endpoints) before exposing to the model."""
    return {k: v for k, v in vendor.items() if k not in _INTERNAL_ONLY_FIELDS}

def internal_tool():
    """Register a tool only when internal tools are enabled on the server."""
    def decorator(func):
        if ENABLE_INTERNAL_TOOLS:
            return mcp.tool()(func)
        return func

    return decorator


def _get_server_api_key() -> str:
    """Resolve the BulkClix API key from the server environment."""
    api_key = os.environ.get("BULKCLIX_API_KEY")
    if not api_key:
        raise RuntimeError("Missing BulkClix API key. Set BULKCLIX_API_KEY on the server.")
    return api_key



def _get_payment_bearer_token() -> str | None:
    """Resolve an optional payment bearer token for OTP verification endpoints."""
    return (
        os.environ.get("BULKCLIX_PAYMENT_BEARER_TOKEN")
        or os.environ.get("BULKCLIX_BEARER_TOKEN")
        or os.environ.get("BULKCLIX_AUTH_TOKEN")
    )


def _get_default_customer_name() -> str:
    """Resolve a default customer/account display name for purchase payloads."""
    return (
        os.environ.get("BULKCLIX_DEFAULT_CUSTOMER_NAME")
        or os.environ.get("BULKCLIX_CUSTOMER_NAME")
        or "BulkClix Customer"
    )


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
    """Return the first sender ID-like field from a sender record."""
    if isinstance(record, str):
        cleaned = record.strip()
        return cleaned or None
    if isinstance(record, dict):
        for key in ("sender_id", "senderId", "id", "uuid", "value", "name"):
            value = record.get(key)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
    return None


async def _get_default_sender_id() -> str:
    """Fetch the first available sender ID from the BulkClix account."""
    response = await _call_api("GET", "/sms-api/senderIds")
    for record in _extract_sender_records(response):
        sender_id = _extract_sender_id(record)
        if sender_id:
            return sender_id
    raise RuntimeError("No sender ID is configured on the BulkClix account.")


def _is_successful_payment_status(payload: Any) -> bool:
    """Detect success from a payment status payload."""
    if payload is True:
        return True
    status_text = _extract_status_text(payload)
    if status_text:
        return status_text in {"success", "successful", "paid", "completed", "approved", "done"}
    if isinstance(payload, dict):
        for key in ("success", "paid", "completed", "approved"):
            if payload.get(key) is True:
                return True
    return False

def _flatten_menu(raw_menu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten Horlap's nested category -> subcategory -> dishes structure into a
    flat list of orderable items. Handles dishes that live directly under a
    category (no subcategory) as well as dishes nested under subcategories —
    both occur in real responses (e.g. category 29 has both).
    """
    items: List[Dict[str, Any]] = []

    def _normalize(dish, category_id, category_name, subcategory_id, subcategory_name):
        try:
            price = float(dish.get("base_price"))
        except (TypeError, ValueError):
            price = None
        return {
            "dish_id": dish.get("id"),
            "name": dish.get("name"),
            "description": dish.get("description") or None,
            "price": price,
            "is_available": bool(dish.get("is_available", False)),
            "category_id": category_id,
            "category": category_name,
            "subcategory_id": subcategory_id,
            "subcategory": subcategory_name,
            "addons": [
                {
                    "addon_id": a.get("id"),
                    "name": a.get("name"),
                    "price": float(a["price"]) if a.get("price") not in (None, "") else None,
                    "is_active": bool(a.get("is_active", False)),
                }
                for a in (dish.get("addons") or [])
            ],
        }

    for category in raw_menu:
        cat_id, cat_name = category.get("id"), category.get("name", "")

        for dish in category.get("dishes") or []:
            items.append(_normalize(dish, cat_id, cat_name, None, None))

        for subcategory in category.get("subcategories") or []:
            sub_id, sub_name = subcategory.get("id"), subcategory.get("name", "")
            for dish in subcategory.get("dishes") or []:
                items.append(_normalize(dish, cat_id, cat_name, sub_id, sub_name))

    return items



def _extract_status_text(payload: Any) -> str | None:
    """Return the most relevant lowercase status string from a nested payload."""
    if isinstance(payload, str):
        cleaned = payload.strip().lower()
        return cleaned or None
    if not isinstance(payload, dict):
        return None

    for key in ("status", "state", "payment_status", "message", "detail", "description"):
        value = payload.get(key)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                return cleaned

    for key in ("data", "payment", "result", "response"):
        nested_value = payload.get(key)
        nested_status = _extract_status_text(nested_value)
        if nested_status:
            return nested_status

    return None


def _extract_payment_records(payload: Any) -> list[Any]:
    """Return payment history records from a payment history response."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    return []


def _payment_status_from_record(record: Any) -> str | None:
    """Return a normalized payment status from a payment record."""
    if not isinstance(record, dict):
        return None

    status_value = record.get("status")
    if isinstance(status_value, str):
        cleaned = status_value.strip().lower()
        if cleaned:
            return cleaned
    return None


def _is_not_found_response(payload: Any) -> bool:
    """Detect a not-found style response from BulkClix."""
    if isinstance(payload, dict):
        error_value = payload.get("error") or payload.get("message")
        if isinstance(error_value, str) and "not found" in error_value.lower():
            return True
    if isinstance(payload, str):
        return "not found" in payload.lower()
    return False


async def _fetch_payment_history(
    *,
    status: str = "undefined",
    search: str = "",
    page_size: int = 5,
    page: int = 1,
) -> Dict[str, Any]:
    """Fetch payment history from BulkClix."""

    bearer_token = _get_payment_bearer_token()
    extra_headers = {}
    if bearer_token:
        extra_headers["Authorization"] = f"Bearer {bearer_token}"

    return await _call_api(
        "GET",
        "/pay/paymentHistory",
        params={
            "status": status,
            "search": search,
            "page_size": page_size,
            "page": page,
        },
        extra_headers=extra_headers or None
    )


def _find_payment_history_match(payload: Any, identifiers: List[str]) -> Dict[str, Any] | None:
    """Find a payment history entry that matches one of the identifiers."""
    identifier_set = {value.strip() for value in identifiers if isinstance(value, str) and value.strip()}
    if not identifier_set:
        return None

    for record in _extract_payment_records(payload):
        if not isinstance(record, dict):
            continue

        candidate_values = {
            record.get("id"),
            record.get("transaction_id"),
            record.get("order_id"),
            record.get("phone_number"),
            record.get("desc"),
        }
        for candidate in candidate_values:
            if isinstance(candidate, str) and candidate in identifier_set:
                return record
    return None


async def _wait_for_payment_confirmation(
    transaction_id: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
) -> Dict[str, Any]:
    """Poll the payment status endpoint until payment clears or times out."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_status: Dict[str, Any] | str | bool | None = None

    while True:
        last_status = await _call_api("GET", f"/pay/checkstatus/{transaction_id}")
        if _is_successful_payment_status(last_status):
            return last_status if isinstance(last_status, dict) else {"status": last_status}

        status_text = _extract_status_text(last_status) or ""

        if status_text in {"failed", "failure", "rejected", "declined", "cancelled", "canceled"}:
            raise RuntimeError(f"Payment was not completed: {last_status}")

        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"Timed out waiting for payment confirmation: {last_status}")

        await asyncio.sleep(poll_interval_seconds)


def _find_bundle_price(payload: Any, bundle_id: str) -> float | None:
    """
    Find a data bundle's price (Amount) inside the nested API response.

    Expected shape (defensively unwrapped, since `payload` is Any):
        {"data": {"packages": {"data": [{"id": ..., "Amount": ...}, ...]}}}

    Returns the Amount as a float if a package with a matching `id`
    is found, otherwise None. Never raises on malformed/missing data.
    """
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    packages = data.get("packages")
    if not isinstance(packages, dict):
        return None

    package_list = packages.get("data")
    if not isinstance(package_list, list):
        return None

    for package in package_list:
        if isinstance(package, dict) and package.get("id") == bundle_id:
            amount = package.get("Amount")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                return float(amount)
            return None

    return None


async def _collect_then_execute(
    *,
    amount: float,
    phone_number: str,
    network: str,
    transaction_id: str | None,
    callback_url: str | None,
    reference: str | None,
    execute_path: str,
    execute_payload: Dict[str, Any],
    await_payment: bool,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> Dict[str, Any]:
    """Collect payment first, then execute the requested service."""
    resolved_transaction_id = transaction_id or f"bulkclix-{uuid4().hex}"
    collection_payload: Dict[str, Any] = {
        "amount": amount,
        "phone_number": phone_number,
        "network": network,
        "transaction_id": resolved_transaction_id,
    }
    if callback_url:
        collection_payload["callback_url"] = callback_url
    if reference:
        collection_payload["reference"] = reference

    collection_response = await _call_api("POST", "/payment-api/momopay", json_data=collection_payload)
    if not await_payment:
        return {
            "status": "payment_pending",
            "transaction_id": resolved_transaction_id,
            "collection": collection_response,
        }

    payment_status = await _wait_for_payment_confirmation(
        resolved_transaction_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    execution_payload = dict(execute_payload)
    execution_payload["transaction_id"] = resolved_transaction_id
    service_response = await _call_api("POST", execute_path, json_data=execution_payload)
    return {
        "status": "completed",
        "transaction_id": resolved_transaction_id,
        "collection": collection_response,
        "payment_status": payment_status,
        "service_response": service_response,
    }

async def _call_api(
    method: str,
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Helper function to run HTTP requests to BulkClix API."""
    headers = {
        "x-api-key": _get_server_api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if extra_headers:
        headers.update(extra_headers)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method,
                url=f"{BASE_URL}{path}",
                headers=headers,
                json=json_data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
            raise RuntimeWarning(f"BulkClix API Error {e.response.status_code}: {error_detail}")
        except Exception as e:
            raise RuntimeWarning(f"Request failed: {str(e)}")
        
async def _call_vendor_api(
    method: str,
    url: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """HTTP helper for third-party vendor APIs. Returns a dict on success OR
    failure — never raises — so callers can check ["success"] uniformly
    instead of needing a try/except around every call site."""
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.request(method=method, url=url, headers=headers, json=json, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
            return {"success": False, "error": f"Vendor API error {e.response.status_code}: {error_detail}"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"Vendor API request failed: {e}"}


# ==============================================================================
# SMS TOOLS
# ==============================================================================

@internal_tool()
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

@internal_tool()
async def sms_get_campaign_report(
    *,
    campaign_id: str
) -> Dict[str, Any]:
    """
    Get the delivery report for a specific SMS campaign.
    :param campaign_id: The campaign ID returned from sms_send.
    """
    return await _call_api( "GET", f"/sms-api/campaignMessages/{campaign_id}")

@internal_tool()
async def senderid_list() -> Dict[str, Any]:
    """
    List all SMS Sender IDs registered on your BulkClix account along with their status.
    """
    return await _call_api( "GET", "/sms-api/senderIds")

@internal_tool()
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

# ==============================================================================
# OTP TOOLS
# ==============================================================================

@mcp.tool()
async def otp_send_sms(
    *,
    phone_number: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via SMS. Use <%otp_code%> placeholder inside your template.
    :param phone_number: Recipient phone number (e.g. '0541000000').
    :param message: Message template containing <%otp_code%> (e.g. 'Code is: <%otp_code%>').
    :param expiry: OTP validity duration in minutes (default 5).
    :param length: Digit length of the OTP (default 4).
    """
    sender_id = await _get_default_sender_id()
    return await _call_api(
        "POST",
        "/sms-api/otp/send",
        json_data={
            "phoneNumber": phone_number,
            "senderId": sender_id,
            "message": message,
            "expiry": expiry,
            "length": length
        }
    )

@mcp.tool()
async def otp_verify_sms(
    *,
    request_id: str,
    phone_number: str,
    code: str
) -> Dict[str, Any]:
    """
    Verify an OTP code that was sent via SMS.
    :param request_id: The requestId returned from sending the OTP.
    :param phone_number: The phone number the OTP was sent to.
    :param code: The code input by the user to check.
    """
    return await _call_api(
        "POST",
        "/sms-api/otp/verify",
        json_data={
            "requestId": request_id,
            "phoneNumber": phone_number,
            "code": code
        }
    )

@mcp.tool()
async def otp_send_email(
    *,
    email: str,
    subject: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via Email. Use <%otp_code%> placeholder.
    :param email: Recipient email address.
    :param subject: Email subject.
    :param message: Email body containing <%otp_code%> template.
    :param expiry: OTP validity duration in minutes (default 5).
    :param length: Digit length of the OTP (default 4).
    """
    return await _call_api(
        "POST",
        "/sms-api/otp/email/send",
        json_data={
            "email": email,
            "subject": subject,
            "message": message,
            "expiry": expiry,
            "length": length
        }
    )

@mcp.tool()
async def otp_verify_email(
    *,
    request_id: str,
    email: str,
    code: str
) -> Dict[str, Any]:
    """
    Verify an OTP code that was sent via Email.
    :param request_id: The requestId returned from sending the OTP.
    :param email: The email address the OTP was sent to.
    :param code: The verification code to verify.
    """
    return await _call_api(
        "POST",
        "/sms-api/otp/email/verify",
        json_data={
            "requestId": request_id,
            "email": email,
            "code": code
        }
    )

# ==============================================================================
# AIRTIME TOOLS
# ==============================================================================

@mcp.tool()
async def airtime_get_networks() -> Dict[str, Any]:
    """
    Get supported networks for airtime top-up.
    """
    return await _call_api( "GET", "/airtime-api/networks")

@mcp.tool()
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
    :param transaction_id: Optional transaction reference. Retained for compatibility.
    :param await_payment: Retained for compatibility with older flows.
    :param timeout_seconds: Retained for compatibility with older flows.
    :param poll_interval_seconds: Retained for compatibility with older flows.
    :param callback_url: Retained for compatibility with older flows.
    :param reference: Retained for compatibility with older flows.
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

@internal_tool()
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

# ==============================================================================
# MOBILE MONEY (PAYMENT) TOOLS
# ==============================================================================

@internal_tool()
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

# TODO: remove the resp["data"]["payment"] ddict to prevent info leaking
@mcp.tool()
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


@mcp.tool()
async def pay_verify_otp(
    *,
    code: str,
    request_id: str,
    phone_number: str
) -> Dict[str, Any]:
    """
    Verify a payment OTP after the customer reads the code from their phone and sends it in chat.
    :param code: OTP code entered by the customer from their phone.
    :param request_id: Request ID returned when the payment was initiated.
    :param phone_number: The phone number used for the payment.
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


@internal_tool()
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

# ==============================================================================
# BANK TRANSFER TOOLS
# ==============================================================================

@internal_tool()
async def bank_transfer_send(
    *,
    amount: float,
    account_number: str,
    account_name: str,
    bank_code: str,
    transaction_id: str,
    narration: Optional[str] = None,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transfer funds from your BulkClix wallet to a bank account.
    :param amount: Transfer amount in GHS.
    :param account_number: Recipient account number.
    :param account_name: Recipient account name.
    :param bank_code: Code of the destination bank.
    :param transaction_id: Unique reference identifier.
    :param narration: Short transaction description.
    :param callback_url: Webhook URL for updates.
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
    return await _call_api( "POST", "/payment-api/bank-transfer", json_data=data)

@internal_tool()
async def bank_list() -> Dict[str, Any]:
    """
    List all supported banks and their bank codes.
    """
    return await _call_api( "GET", "/payment-api/banks")

# ==============================================================================
# DATA BUNDLE TOOLS
# ==============================================================================

@mcp.tool()
async def data_get_bundles(
    *,
    network_id: str | None = None
) -> Dict[str, Any]:
    """
    List available data bundle services.
    """
    return await _call_api("GET", "/databundle-api-v2/services")


@mcp.tool()
async def data_get_offers(
    *,
    service_id: str,
    phone_number: str
) -> Dict[str, Any]:
    """
    List available data bundle offers for a service and phone number.
    :param service_id: Data service UUID.
    :param phone_number: Recipient phone number.
    """
    return await _call_api(
        "GET",
        f"/databundle-api-v2/offers/{service_id}/{phone_number}",
    )

@mcp.tool()
async def data_purchase(
    *,
    phone_number: str,
    bundle_id: str,
    network_id: str,
    service_id: str,
    network: str,
    customer_name: str | None = None,
    transaction_id: str | None = None,
    await_payment: bool = True,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
    callback_url: str | None = None,
    reference: str | None = None,
) -> Dict[str, Any]:
    """
    Start a data bundle purchase using the BulkClix purchase route.
    :param phone_number: Recipient phone number.
    :param bundle_id: UUID of the data bundle package to buy.
    :param network_id: UUID of the network.
    :param service_id: UUID of the data package service, use data_get_bundles to get.
    :param network: Payer network code (e.g., 'MTN', 'VDF', 'ATL').
    :param customer_name: Optional display name used by the purchase API.
    :param transaction_id: Optional transaction reference. A unique one is generated if omitted.
    :param await_payment: Retained for compatibility with older flows.
    :param timeout_seconds: Retained for compatibility with older flows.
    :param poll_interval_seconds: Retained for compatibility with older flows.
    :param callback_url: Retained for compatibility with older flows.
    :param reference: Retained for compatibility with older flows.
    """
    bundle_catalog = await data_get_offers(service_id=service_id, phone_number=phone_number)
    bundle_amount = _find_bundle_price(bundle_catalog, bundle_id)
    if bundle_amount is None:
        raise RuntimeError(f"Could not determine the bundle price for {bundle_id}.")

    purchase_payload: Dict[str, Any] = {
        "destination": phone_number,
        "phone_number": phone_number,
        "amount": bundle_amount,
        "service_id": service_id,
        "name": customer_name or _get_default_customer_name(),
        "package_id": bundle_id,
        "network": network,
        "type": "momo",
    }
    if transaction_id:
        purchase_payload["transaction_id"] = transaction_id
    if callback_url:
        purchase_payload["callback_url"] = callback_url
    if reference:
        purchase_payload["reference"] = reference

    return await _call_api(
        "POST",
        "/databundle-api-v2/buy",
        json_data=purchase_payload,
    )


@mcp.tool()
async def data_check_status(
    *,
    order_id: str,
    payment_id: str | None = None,
    transaction_id: str | None = None
) -> Dict[str, Any]:
    """
    Check the status of a data bundle payment or purchase by order ID.
    :param order_id: The order ID returned when the data purchase was initiated.
    :param payment_id: Optional payment record ID from the purchase response.
    :param transaction_id: Optional payment transaction ID from the purchase response.
    """
    resolved_payment_id = payment_id
    history_search_terms = [order_id]
    if transaction_id:
        history_search_terms.append(transaction_id)
    if not resolved_payment_id:
        history = await _fetch_payment_history(search=order_id, page_size=25)
        matched_record = _find_payment_history_match(history, history_search_terms)
        if matched_record:
            resolved_payment_id = matched_record.get("id") if isinstance(matched_record.get("id"), str) else None
            if not transaction_id:
                transaction_value = matched_record.get("transaction_id")
                if isinstance(transaction_value, str):
                    transaction_id = transaction_value

    lookup_id = resolved_payment_id or order_id
    status_response = await _call_api("GET", f"/pay/checkDataStatus/{lookup_id}")
    if _is_not_found_response(status_response):
        history = await _fetch_payment_history(search=order_id, page_size=25)
        matched_record = _find_payment_history_match(history, [order_id, lookup_id] + ([transaction_id] if transaction_id else []))
        if matched_record:
            return {
                "status": _payment_status_from_record(matched_record) or "unknown",
                "record": matched_record,
                "source": "payment_history",
            }
    return status_response

# ==============================================================================
# KYC TOOLS
# ==============================================================================

@internal_tool()
async def kyc_msisdn_name_query(
    *,
    phone_number: str
) -> Dict[str, Any]:
    """
    Look up the registered owner's name for a phone number.
    :param phone_number: Target phone number (e.g. '0541008285').
    """
    return await _call_api( "GET", "/kyc-api/msisdNameQuery", params={"phone_number": phone_number})

# ==============================================================================
# CONTACTS & GROUPS TOOLS
# ==============================================================================

@internal_tool()
async def contacts_list_groups() -> Dict[str, Any]:
    """
    List contact groups configured on your account.
    """
    return await _call_api( "GET", "/sms-api/contact/getGroups")

@internal_tool()
async def contacts_create_group(
    *,
    name: str,
    group_icon: str = "group_icon_1"
) -> Dict[str, Any]:
    """
    Create a new contact group.
    :param name: Group name.
    :param group_icon: Icon identifier key (default 'group_icon_1').
    """
    return await _call_api(
        "POST",
        "/sms-api/contact/addGroup",
        json_data={"name": name, "group_icon": group_icon}
    )

@internal_tool()
async def contacts_update_group(
    *,
    group_id: str,
    name: str,
    group_icon: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update details of a contact group.
    :param group_id: Group UUID.
    :param name: New name for the group.
    :param group_icon: Optional new icon key.
    """
    data = {"name": name}
    if group_icon:
        data["group_icon"] = group_icon
    return await _call_api( "PATCH", f"/sms-api/contact/updateGroup/{group_id}", json_data=data)

@internal_tool()
async def contacts_delete_group(
    *,
    group_id: str
) -> Dict[str, Any]:
    """
    Delete a contact group.
    :param group_id: Group UUID to delete.
    """
    return await _call_api( "DELETE", f"/sms-api/contact/deleteGroup/{group_id}")

@internal_tool()
async def contacts_list(
    *,
    group_id: str
) -> Dict[str, Any]:
    """
    List all contacts inside a specific group.
    :param group_id: Group UUID.
    """
    return await _call_api( "GET", f"/sms-api/contact/getContacts/{group_id}")

@internal_tool()
async def contacts_add(
    *,
    first_name: str,
    last_name: str,
    phone_number: str,
    contact_group_id: str,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a single contact to a group.
    :param first_name: First name of the contact.
    :param last_name: Last name of the contact.
    :param phone_number: Phone number of the contact.
    :param contact_group_id: UUID of the target group.
    :param email: Optional email address.
    """
    data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "contact_group_id": contact_group_id
    }
    if email:
        data["email"] = email
    return await _call_api( "POST", "/sms-api/contact/addContact", json_data=data)

@internal_tool()
async def contacts_add_bulk(
    *,
    contact_group_id: str,
    contacts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add multiple contacts to a contact group.
    :param contact_group_id: UUID of the target group.
    :param contacts: A list of dicts, each with keys: first_name, last_name, phone_number, and optional email.
    """
    return await _call_api(
        "POST",
        "/sms-api/contact/addBulkContact",
        json_data={
            "contact_group_id": contact_group_id,
            "contacts": contacts
        }
    )

@internal_tool()
async def contacts_update(
    *,
    contact_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update contact details.
    :param contact_id: Contact UUID.
    :param first_name: New first name.
    :param last_name: New last name.
    :param phone_number: New phone number.
    """
    data = {}
    if first_name:
        data["first_name"] = first_name
    if last_name:
        data["last_name"] = last_name
    if phone_number:
        data["phone_number"] = phone_number
    return await _call_api( "PATCH", f"/sms-api/contact/updateContact/{contact_id}", json_data=data)

@internal_tool()
async def contacts_delete(
    *,
    contact_id: str
) -> Dict[str, Any]:
    """
    Delete a contact.
    :param contact_id: Contact UUID to delete.
    """
    return await _call_api( "DELETE", f"/sms-api/contact/deleteContact/{contact_id}")

# ==============================================================================
# ACCOUNT / WALLET TOOLS
# ==============================================================================

@internal_tool()
async def account_wallet_balance() -> Dict[str, Any]:
    """
    Check your BulkClix wallet balance.
    """
    return await _call_api( "GET", "/account/balance")



# ==============================================================================
# VENDOR TOOLS
# ==============================================================================



@mcp.tool()
async def get_verified_vendors(
    *,
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List available vendors to purchase goods from using BulkClix payment.
    :param vendor_id: Vendor's UUID. If given, returns just that vendor.
    :param category: Vendor's category of goods (e.g. "restaurant"). If given,
        filters to vendors whose `categories` list contains a case-insensitive match.
    """
    if vendor_id:
        vendor = _lookup_vendor(vendor_id)
        if vendor is None:
            return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}
        return {"success": True, "vendors": [_public_vendor_view(vendor)]}

    vendors = STATIC_VENDORS_LIST
    if category:
        q = category.lower()
        vendors = [
            v for v in vendors
            if any(q in c.lower() or c.lower() in q for c in v.get("categories", []))
        ]

    return {"success": True, "vendors": [_public_vendor_view(v) for v in vendors]}

@mcp.tool()
async def get_verified_vendors_menu(
    *,
    vendor_id: str,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List available menu items for a vendor, flattened and checkout-ready —
    each item has dish_id, name, price, is_available, and addons. No nested
    categories.
    :param vendor_id: Vendor's UUID.
    :param query: Optional case-insensitive substring filter on dish name.
        Filtering is done locally — Horlap's menu endpoint returns the full
        menu regardless of query params.
    """
    vendor = _lookup_vendor(vendor_id)
    if vendor is None:
        return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}

    raw_response = await _call_vendor_api("GET", vendor["menu_url"])

    if isinstance(raw_response, dict) and raw_response.get("success") is False:
        return raw_response  # propagate HTTP/network error from _call_vendor_api

    if not isinstance(raw_response, list):
        return {"success": False, "error": "Unexpected menu response shape from vendor"}

    items = _flatten_menu(raw_response)

    if query:
        q = query.lower()
        items = [i for i in items if q in (i["name"] or "").lower()]

    return {"success": True, "items": items}

@mcp.tool()
async def create_verified_vendors_order(
    *,
    vendor_id: str,
    items: List[Dict[str, Any]],
    payment_number: str,
    network: str,
    order_type: str = "inhouse",
    table_number: Optional[str] = None,
    delivery_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Place an order with a vendor and initiate mobile money payment via BulkClix.
    :param vendor_id: Vendor's UUID.
    :param items: Items to order, each shaped like
        {"dish_id": <int>, "quantity": <int>, "addon_ids": [<int>, ...]}.
    :param payment_number: Mobile money number to charge (e.g. "0544929180").
    :param network: Mobile money network code (e.g. "MTN").
    :param order_type: "inhouse" or "delivery" — must be one of the vendor's supported order_types.
    :param table_number: Table number. Required when order_type is "inhouse".
    :param delivery_address: Delivery address. Required when order_type is "delivery".
    """
    try:
        vendor = _lookup_vendor(vendor_id)
        if vendor is None:
            return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}

        if "momo" not in vendor.get("payment_methods", []):
            return {"success": False, "error": f"Vendor {vendor_id!r} does not support mobile money payment"}

        supported_order_types = vendor.get("order_types", [])
        if order_type not in supported_order_types:
            return {
                "success": False,
                "error": f"Vendor {vendor_id!r} does not support order_type {order_type!r} "
                         f"(supported: {supported_order_types})",
            }
        if order_type == "inhouse" and not table_number:
            return {"success": False, "error": "table_number is required for inhouse orders"}
        if order_type == "delivery" and not delivery_address:
            return {"success": False, "error": "delivery_address is required for delivery orders"}

        menu_result = await get_verified_vendors_menu(vendor_id=vendor_id)
        if not menu_result["success"]:
            return {"success": False, "error": f"Could not verify menu before ordering: {menu_result['error']}"}

        menu_by_id = {item["dish_id"]: item for item in menu_result["items"]}
        for line in items:
            dish = menu_by_id.get(line.get("dish_id"))
            if dish is None:
                return {"success": False, "error": f"dish_id {line.get('dish_id')!r} not found on vendor's menu"}
            if not dish["is_available"]:
                return {"success": False, "error": f"{dish['name']!r} (dish_id {dish['dish_id']}) is currently unavailable"}

        order_url = vendor.get("order_url")
        if not order_url:
            return {"success": False, "error": f"Vendor {vendor_id!r} has no configured order endpoint"}

        payload = {
            "order_type": order_type,
            "table_number": table_number,
            "items": items,
            "payment_number": payment_number,
            "network": network,
        }
        if order_type == "delivery":
            payload["delivery_address"] = delivery_address

        return await _call_vendor_api("POST", order_url, json=payload)
    except Exception as e:
        # Safety net: never let an unexpected error escape as an uncaught
        # exception mid-tool-call — that's what corrupts the transport.
        return {"success": False, "error": f"Unexpected error placing order: {e}"}







if __name__ == "__main__":
    import sys
    # If "mcp" or "sse" is passed as an argument, run as remote transport, else run as stdio (default)
    if len(sys.argv) > 1 and sys.argv[1].lower() in {"mcp", "sse"}:
        print("Starting BulkClix MCP server on SSE transport (http://localhost:8000/sse)...", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")