from typing import Any, Dict, List, Optional
from mcp.types import ToolAnnotations
from app import general as mcp
from http_client import _call_api

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def contacts_list_groups() -> Dict[str, Any]:
    """
    List contact groups configured on your account.
    """
    return await _call_api("GET", "/sms-api/contact/getGroups")

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def contacts_create_group(
    *,
    name: str,
    group_icon: str = "group_icon_1"
) -> Dict[str, Any]:
    """
    Create a new contact group.
    """
    return await _call_api(
        "POST",
        "/sms-api/contact/addGroup",
        json_data={"name": name, "group_icon": group_icon}
    )

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def contacts_update_group(
    *,
    group_id: str,
    name: str,
    group_icon: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update details of a contact group.
    """
    data = {"name": name}
    if group_icon:
        data["group_icon"] = group_icon
    return await _call_api("PATCH", f"/sms-api/contact/updateGroup/{group_id}", json_data=data)

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def contacts_delete_group(
    *,
    group_id: str
) -> Dict[str, Any]:
    """
    Delete a contact group.
    """
    return await _call_api("DELETE", f"/sms-api/contact/deleteGroup/{group_id}")

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def contacts_list(
    *,
    group_id: str
) -> Dict[str, Any]:
    """
    List all contacts inside a specific group.
    """
    return await _call_api("GET", f"/sms-api/contact/getContacts/{group_id}")

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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
    """
    data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "contact_group_id": contact_group_id
    }
    if email:
        data["email"] = email
    return await _call_api("POST", "/sms-api/contact/addContact", json_data=data)

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def contacts_add_bulk(
    *,
    contact_group_id: str,
    contacts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add multiple contacts to a contact group.
    """
    return await _call_api(
        "POST",
        "/sms-api/contact/addBulkContact",
        json_data={
            "contact_group_id": contact_group_id,
            "contacts": contacts
        }
    )

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def contacts_update(
    *,
    contact_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update contact details.
    """
    data = {}
    if first_name:
        data["first_name"] = first_name
    if last_name:
        data["last_name"] = last_name
    if phone_number:
        data["phone_number"] = phone_number
    return await _call_api("PATCH", f"/sms-api/contact/updateContact/{contact_id}", json_data=data)

@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def contacts_delete(
    *,
    contact_id: str
) -> Dict[str, Any]:
    """
    Delete a contact.
    """
    return await _call_api("DELETE", f"/sms-api/contact/deleteContact/{contact_id}")
