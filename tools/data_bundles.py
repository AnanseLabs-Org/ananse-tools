from mcp.types import ToolAnnotations
from typing import Any, Dict
from app import general as mcp
from http_client import _call_api
from auth import _get_default_customer_name
from payments.helpers import _fetch_payment_history, _find_payment_history_match, _is_not_found_response, _payment_status_from_record

def _find_bundle_price(payload: Any, bundle_id: str) -> float | None:
    """
    Find a data bundle's price (Amount) inside the nested API response.
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

@mcp.tool(
    description="List available data bundle services.",
    tags={"role:data_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def data_get_bundles(
    *,
    network_id: str | None = None
) -> Dict[str, Any]:
    """
    List available data bundle services.
    """
    return await _call_api("GET", "/databundle-api-v2/services")


@mcp.tool(
    description="List available data bundle offers for a service and phone number. :param service_id: Data service UUID. :param phone_number: Recipient phone number.",
    tags={"role:data_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
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

@mcp.tool(
    description="Start a data bundle purchase using the BulkClix purchase route.",
    tags={"role:data_user"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
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


@mcp.tool(
    description="Check the status of a data bundle payment or purchase by order ID.",
    tags={"role:data_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def data_check_status(
    *,
    order_id: str,
    payment_id: str | None = None,
    transaction_id: str | None = None
) -> Dict[str, Any]:
    """
    Check the status of a data bundle payment or purchase by order ID.
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
