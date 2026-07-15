import os

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


def _get_default_callback_url() -> str:
    """Resolve a default callback URL for MoMo transactions, required by BulkClix."""
    return (
        os.environ.get("BULKCLIX_CALLBACK_URL")
        or "https://webhook.site/422f6a65-71eb-482c-a673-0ad3ecae8efc"
    )

