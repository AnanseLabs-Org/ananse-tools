from typing import Any, Dict, List

def _flatten_menu(raw_menu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten Horlap's nested category -> subcategory -> dishes structure into a
    flat list of orderable items.
    """
    items: List[Dict[str, Any]] = []

    def _normalize(dish, category_id, category_name, subcategory_id, subcategory_name):
        try:
            price = float(dish.get("base_price"))
        except (TypeError, ValueError):
            price = None
        img = dish.get("image_url") or dish.get("image") or None
        return {
            "dish_id": dish.get("id"),
            "name": dish.get("name"),
            "description": dish.get("description") or None,
            "price": price,
            "image": img,
            "image_url": img,
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
