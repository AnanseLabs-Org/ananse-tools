import asyncio
from typing import Any, Dict, List, Optional
from uuid import uuid4
from http_client import _call_api
from auth import _get_payment_bearer_token, _get_default_callback_url

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
        "callback_url": callback_url or _get_default_callback_url(),
    }
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
