from mcp.types import ToolAnnotations
from typing import Any, Dict
from app import mcp
from http_client import _call_api
from tools.sms import _get_default_sender_id

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def otp_send_sms(
    *,
    phone_number: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via SMS.
    CRITICAL: The `message` parameter MUST contain the exact placeholder `<%otp_code%>`. If this placeholder is missing, the API call will fail with a 422 error.
    
    :param phone_number: Recipient phone number (e.g. '0541000000').
    :param message: Message template containing `<%otp_code%>` (e.g. 'Your verification code is: <%otp_code%>').
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

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def otp_send_email(
    *,
    email: str,
    subject: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via Email.
    CRITICAL: The `message` parameter MUST contain the exact placeholder `<%otp_code%>`. If this placeholder is missing, the API call will fail with a 422 error.
    
    :param email: Recipient email address.
    :param subject: Email subject.
    :param message: Email body containing `<%otp_code%>` template (e.g. 'Your verification code is: <%otp_code%>').
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

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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
