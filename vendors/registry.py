from typing import Any, Dict, Optional

STATIC_VENDORS_LIST = [
    {
        "vendor_id": "234490c6-09e1-4125-b9cd-506d64eb2c50",
        "name": "Horlap",
        "categories": ["restaurant", "food_delivery", "food"],
        "order_types": ["inhouse"],
        "menu_url": "https://api.horlap.com/api/menu/",
        "order_url": "https://api.horlap.com/api/orders/create-and-initiate-payment/",
        "payment_methods": ["momo"],
        "vendor_type": "external_api"
    },
    {
        "vendor_id": "f5f0b5aa-399a-4c28-98b7-6b6f3ff8cfa0",
        "name": "MTN Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "MTN",
        "payment_methods": ["momo"]
    },
    {
        "vendor_id": "a90b4cc5-5c12-4217-bfd2-c76a54f0a99c",
        "name": "Telecel Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "TELECEL",
        "payment_methods": ["momo"]
    },
    {
        "vendor_id": "d02fa3c5-92a0-410a-8bf7-e16fa5cfc99b",
        "name": "AirtelTigo Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "AIRTELTIGO",
        "payment_methods": ["momo"]
    }
]

_INTERNAL_ONLY_FIELDS = {"menu_url", "order_url"}


def _lookup_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    """
    Internal lookup returning the FULL vendor record, including API endpoints.
    """
    return next((v for v in STATIC_VENDORS_LIST if v["vendor_id"] == vendor_id), None)


def _public_vendor_view(vendor: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal-only fields (API endpoints) before exposing to the model."""
    return {k: v for k, v in vendor.items() if k not in _INTERNAL_ONLY_FIELDS}


def _expand_category_query(query: str) -> set[str]:
    """Expand category query with synonyms to improve discoverability."""
    synonyms = {
        "food": {"restaurant", "dining", "takeout", "delivery", "eatery", "cafe", "fast food", "dishes", "meals"},
        "restaurant": {"food", "dining", "eatery", "cafe", "fast food", "meals"},
        "dining": {"food", "restaurant", "eatery"},
        "delivery": {"takeout", "food", "restaurant"},
        "takeout": {"delivery", "food", "restaurant"},
    }
    q = query.lower().strip()
    expanded = {q}
    for key, syn_set in synonyms.items():
        if q == key or q in syn_set:
            expanded.add(key)
            expanded.update(syn_set)
    return expanded
