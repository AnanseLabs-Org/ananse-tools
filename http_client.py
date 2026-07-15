import httpx
import logging
from typing import Any, Dict, Optional
from config import BASE_URL
from auth import _get_server_api_key

logger = logging.getLogger(__name__)

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
    
    url = f"{BASE_URL}{path}"
    logger.info("BulkClix API Request: %s %s - json=%s - params=%s", method, url, json_data, params)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params
            )
            logger.info("BulkClix API Response Status: %d - Content-Type: %s - Body: %r", 
                        response.status_code, response.headers.get("content-type"), response.text)
            response.raise_for_status()
            if not response.text.strip():
                return {"success": True}
            try:
                return response.json()
            except Exception:
                return {"success": True, "raw_response": response.text}
        except httpx.HTTPStatusError as e:
            logger.error("BulkClix API HTTPStatusError %d: %s", e.response.status_code, e.response.text)
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
            raise RuntimeWarning(f"BulkClix API Error {e.response.status_code}: {error_detail}")
        except Exception as e:
            logger.error("BulkClix API request failed: %s", str(e), exc_info=True)
            raise RuntimeWarning(f"Request failed: {str(e)}")



async def _call_vendor_api(
    method: str,
    url: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """HTTP helper for third-party vendor APIs. Returns a dict on success OR
    failure — never raises — so callers can check ["success"] uniformly."""
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
