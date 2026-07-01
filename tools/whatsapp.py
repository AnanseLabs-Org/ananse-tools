import os
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app import mcp
from db import _get_db
from mcp.types import ToolAnnotations

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def whatsapp_send(
    *,
    to_number: str,
    body: str
) -> Dict[str, Any]:
    """
    Send a WhatsApp message using Twilio's API.
    :param to_number: The recipient's phone number or WhatsApp ID (e.g. "+233241234567" or "whatsapp:+233241234567").
    :param body: The text message content to send.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return {
            "success": False,
            "error": "Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) are not set in the environment variables."
        }

    # Normalize recipient WhatsApp prefix
    raw_to = to_number.strip()
    has_whatsapp_prefix = raw_to.startswith("whatsapp:")
    phone_part = raw_to[9:] if has_whatsapp_prefix else raw_to
    phone_part = phone_part.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    if phone_part.startswith("0") and len(phone_part) == 10:
        phone_part = f"+233{phone_part[1:]}"
    elif phone_part.startswith("233") and not phone_part.startswith("+"):
        phone_part = f"+{phone_part}"
    elif not phone_part.startswith("+"):
        phone_part = f"+{phone_part}"
        
    formatted_to = f"whatsapp:{phone_part}"

    # Normalize sender WhatsApp prefix
    raw_from = TWILIO_WHATSAPP_FROM.strip()
    has_whatsapp_from_prefix = raw_from.startswith("whatsapp:")
    from_phone_part = raw_from[9:] if has_whatsapp_from_prefix else raw_from
    from_phone_part = from_phone_part.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    if from_phone_part.startswith("0") and len(from_phone_part) == 10:
        from_phone_part = f"+233{from_phone_part[1:]}"
    elif from_phone_part.startswith("233") and not from_phone_part.startswith("+"):
        from_phone_part = f"+{from_phone_part}"
    elif not from_phone_part.startswith("+"):
        from_phone_part = f"+{from_phone_part}"
        
    formatted_from = f"whatsapp:{from_phone_part}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    
    data = {
        "From": formatted_from,
        "To": formatted_to,
        "Body": body
    }

    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, data=data, auth=auth)
            if response.status_code in (200, 201):
                res_data = response.json()
                return {
                    "success": True,
                    "message_sid": res_data.get("sid"),
                    "status": res_data.get("status"),
                    "to": formatted_to,
                    "from": TWILIO_WHATSAPP_FROM
                }
            else:
                return {
                    "success": False,
                    "error": f"Twilio API Error {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {"success": False, "error": f"Failed to send WhatsApp message: {str(e)}"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def whatsapp_get_messages(
    *,
    limit: int = 20,
    phone_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve recent incoming WhatsApp messages from MongoDB.
    :param limit: Maximum number of messages to return (default is 20).
    :param phone_number: Optional phone number to filter messages from a specific customer.
    """
    try:
        db = _get_db()
        if db is None:
            return {"success": False, "error": "Database connection is not available."}

        query = {}
        if phone_number:
            formatted_num = phone_number
            if not formatted_num.startswith("whatsapp:"):
                formatted_num = f"whatsapp:{formatted_num}"
            query["from"] = formatted_num

        cursor = db.whatsapp_messages.find(query, {"_id": 0}).sort("received_at", -1).limit(limit)
        messages = await cursor.to_list(length=limit)

        # Convert datetime objects to ISO strings for JSON serialization
        for msg in messages:
            if isinstance(msg.get("received_at"), datetime):
                msg["received_at"] = msg["received_at"].isoformat()

        return {
            "success": True,
            "count": len(messages),
            "messages": messages
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to retrieve messages: {str(e)}"}
