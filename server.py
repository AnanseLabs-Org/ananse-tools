#!/usr/bin/env python3
"""
BulkClix MCP Server (Python / FastMCP edition)
==============================================
An AI agent portal for interacting with the BulkClix platform.
Supports: SMS, Airtime, Data Bundles, Mobile Money, Bank Transfers, OTP, KYC, Contacts.

Authentication: Users provide their API key as a tool argument.
"""

from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP
import httpx

# Initialize FastMCP Server
mcp = FastMCP(
    "bulkclix-mcp"
)

BASE_URL = "https://api.bulkclix.com/api/v1"

async def _call_api(
    api_key: Optional[str],
    method: str,
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Helper function to run HTTP requests to BulkClix API."""
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
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

# ==============================================================================
# SMS TOOLS
# ==============================================================================

@mcp.tool()
async def sms_send(
    *,
    api_key: Optional[str] = None,
    sender_id: str,
    message: str,
    recipients: List[str]
) -> Dict[str, Any]:
    """
    Send an SMS message to one or many phone numbers (bulk SMS).
    
    :param api_key: Your BulkClix API key.
    :param sender_id: UUID of an approved Sender ID from your account.
    :param message: The text message content to send.
    :param recipients: List of recipient phone numbers (e.g. ["0541008285", "0265951172"]).
    """
    return await _call_api(
        api_key, 
        "POST", 
        "/sms-api/send", 
        json_data={
            "sender_id": sender_id,
            "message": message,
            "recipients": recipients
        }
    )

@mcp.tool()
async def sms_get_campaign_report(
    *,
    api_key: Optional[str] = None,
    campaign_id: str
) -> Dict[str, Any]:
    """
    Get the delivery report for a specific SMS campaign.
    
    :param api_key: Your BulkClix API key.
    :param campaign_id: The campaign ID returned from sms_send.
    """
    return await _call_api(api_key, "GET", f"/sms-api/campaignMessages/{campaign_id}")

@mcp.tool()
async def senderid_list(*,
    api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    List all SMS Sender IDs registered on your BulkClix account along with their status.
    
    :param api_key: Your BulkClix API key.
    """
    return await _call_api(api_key, "GET", "/sms-api/senderIds")

@mcp.tool()
async def senderid_request(
    *,
    api_key: Optional[str] = None,
    name: str,
    desc: str
) -> Dict[str, Any]:
    """
    Request a new Sender ID for your BulkClix account.
    
    :param api_key: Your BulkClix API key.
    :param name: The Sender ID name (max 11 alphanumeric characters).
    :param desc: Purpose/description of what this Sender ID will be used for.
    """
    return await _call_api(
        api_key,
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
    api_key: Optional[str] = None,
    phone_number: str,
    sender_id: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via SMS. Use <%otp_code%> placeholder inside your template.
    
    :param api_key: Your BulkClix API key.
    :param phone_number: Recipient phone number (e.g. '0541000000').
    :param sender_id: UUID of an approved Sender ID.
    :param message: Message template containing <%otp_code%> (e.g. 'Code is: <%otp_code%>').
    :param expiry: OTP validity duration in minutes (default 5).
    :param length: Digit length of the OTP (default 4).
    """
    return await _call_api(
        api_key,
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
    api_key: Optional[str] = None,
    request_id: str,
    phone_number: str,
    code: str
) -> Dict[str, Any]:
    """
    Verify an OTP code that was sent via SMS.
    
    :param api_key: Your BulkClix API key.
    :param request_id: The requestId returned from sending the OTP.
    :param phone_number: The phone number the OTP was sent to.
    :param code: The code input by the user to check.
    """
    return await _call_api(
        api_key,
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
    api_key: Optional[str] = None,
    email: str,
    subject: str,
    message: str,
    expiry: int = 5,
    length: int = 4
) -> Dict[str, Any]:
    """
    Send an OTP (One-Time Password) via Email. Use <%otp_code%> placeholder.
    
    :param api_key: Your BulkClix API key.
    :param email: Recipient email address.
    :param subject: Email subject.
    :param message: Email body containing <%otp_code%> template.
    :param expiry: OTP validity duration in minutes (default 5).
    :param length: Digit length of the OTP (default 4).
    """
    return await _call_api(
        api_key,
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
    api_key: Optional[str] = None,
    request_id: str,
    email: str,
    code: str
) -> Dict[str, Any]:
    """
    Verify an OTP code that was sent via Email.
    
    :param api_key: Your BulkClix API key.
    :param request_id: The requestId returned from sending the OTP.
    :param email: The email address the OTP was sent to.
    :param code: The verification code to verify.
    """
    return await _call_api(
        api_key,
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
async def airtime_get_networks(*,
    api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Get supported networks for airtime top-up.
    
    :param api_key: Your BulkClix API key.
    """
    return await _call_api(api_key, "GET", "/airtime-api/networks")

@mcp.tool()
async def airtime_purchase(
    *,
    api_key: Optional[str] = None,
    destination: str,
    phone_number: str,
    network: str,
    amount: float,
    network_id: str,
    payment_type: str = "momo"
) -> Dict[str, Any]:
    """
    Charge a MoMo wallet to send airtime to a destination.
    
    :param api_key: Your BulkClix API key.
    :param destination: Recipient phone number receiving the airtime.
    :param phone_number: MoMo phone number being charged for payment.
    :param network: Payer network code (e.g., 'MTN', 'VDF', 'ATL').
    :param amount: Airtime purchase amount in GHS.
    :param network_id: Network UUID from airtime_get_networks.
    :param payment_type: Payment type (usually 'momo').
    """
    return await _call_api(
        api_key,
        "POST",
        "/airtime-api/buy",
        json_data={
            "destination": destination,
            "phoneNumber": phone_number,
            "network": network,
            "amount": amount,
            "network_id": network_id,
            "type": payment_type
        }
    )

@mcp.tool()
async def airtime_send(
    *,
    api_key: Optional[str] = None,
    phone_number: str,
    network_id: str,
    amount: float,
    transaction_id: str
) -> Dict[str, Any]:
    """
    Send airtime directly to a recipient number using your BulkClix wallet balance.
    
    :param api_key: Your BulkClix API key.
    :param phone_number: Recipient phone number.
    :param network_id: Network UUID from airtime_get_networks.
    :param amount: Airtime amount in GHS.
    :param transaction_id: Your unique transaction reference.
    """
    return await _call_api(
        api_key,
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

@mcp.tool()
async def momo_collect(
    *,
    api_key: Optional[str] = None,
    amount: float,
    phone_number: str,
    network: str,
    transaction_id: str,
    callback_url: Optional[str] = None,
    reference: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initiate a Mobile Money collection — prompts the customer to approve payment.
    
    :param api_key: Your BulkClix API key.
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
    return await _call_api(api_key, "POST", "/payment-api/momopay", json_data=data)

@mcp.tool()
async def momo_check_status(
    *,
    api_key: Optional[str] = None,
    transaction_id: str
) -> Dict[str, Any]:
    """
    Check the status of a Mobile Money collection or transaction.
    
    :param api_key: Your BulkClix API key.
    :param transaction_id: The transaction ID used during collection.
    """
    return await _call_api(api_key, "GET", f"/payment-api/checkstatus/{transaction_id}")

@mcp.tool()
async def momo_disburse(
    *,
    api_key: Optional[str] = None,
    amount: float,
    phone_number: str,
    network: str,
    transaction_id: str,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send/disburse money from your BulkClix wallet balance to a MoMo phone number.
    
    :param api_key: Your BulkClix API key.
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
    return await _call_api(api_key, "POST", "/payment-api/disburse", json_data=data)

# ==============================================================================
# BANK TRANSFER TOOLS
# ==============================================================================

@mcp.tool()
async def bank_transfer_send(
    *,
    api_key: Optional[str] = None,
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
    
    :param api_key: Your BulkClix API key.
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
    return await _call_api(api_key, "POST", "/payment-api/bank-transfer", json_data=data)

@mcp.tool()
async def bank_list(*,
    api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    List all supported banks and their bank codes.
    
    :param api_key: Your BulkClix API key.
    """
    return await _call_api(api_key, "GET", "/payment-api/banks")

# ==============================================================================
# DATA BUNDLE TOOLS
# ==============================================================================

@mcp.tool()
async def data_get_bundles(
    *,
    api_key: Optional[str] = None,
    network_id: str
) -> Dict[str, Any]:
    """
    List available data bundles for a specific network.
    
    :param api_key: Your BulkClix API key.
    :param network_id: Network UUID.
    """
    return await _call_api(api_key, "GET", "/data-api/bundles", params={"network_id": network_id})

@mcp.tool()
async def data_purchase(
    *,
    api_key: Optional[str] = None,
    phone_number: str,
    bundle_id: str,
    network_id: str,
    transaction_id: str
) -> Dict[str, Any]:
    """
    Purchase a data bundle package.
    
    :param api_key: Your BulkClix API key.
    :param phone_number: Recipient phone number.
    :param bundle_id: UUID of the data bundle package to buy.
    :param network_id: UUID of the network.
    :param transaction_id: Unique transaction reference.
    """
    return await _call_api(
        api_key,
        "POST",
        "/data-api/buy",
        json_data={
            "phone_number": phone_number,
            "bundle_id": bundle_id,
            "network_id": network_id,
            "transaction_id": transaction_id
        }
    )

# ==============================================================================
# KYC TOOLS
# ==============================================================================

@mcp.tool()
async def kyc_msisdn_name_query(
    *,
    api_key: Optional[str] = None,
    phone_number: str
) -> Dict[str, Any]:
    """
    Look up the registered owner's name for a phone number.
    
    :param api_key: Your BulkClix API key.
    :param phone_number: Target phone number (e.g. '0541008285').
    """
    return await _call_api(api_key, "GET", "/kyc-api/msisdNameQuery", params={"phone_number": phone_number})

# ==============================================================================
# CONTACTS & GROUPS TOOLS
# ==============================================================================

@mcp.tool()
async def contacts_list_groups(*,
    api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    List contact groups configured on your account.
    
    :param api_key: Your BulkClix API key.
    """
    return await _call_api(api_key, "GET", "/sms-api/contact/getGroups")

@mcp.tool()
async def contacts_create_group(
    *,
    api_key: Optional[str] = None,
    name: str,
    group_icon: str = "group_icon_1"
) -> Dict[str, Any]:
    """
    Create a new contact group.
    
    :param api_key: Your BulkClix API key.
    :param name: Group name.
    :param group_icon: Icon identifier key (default 'group_icon_1').
    """
    return await _call_api(
        api_key,
        "POST",
        "/sms-api/contact/addGroup",
        json_data={"name": name, "group_icon": group_icon}
    )

@mcp.tool()
async def contacts_update_group(
    *,
    api_key: Optional[str] = None,
    group_id: str,
    name: str,
    group_icon: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update details of a contact group.
    
    :param api_key: Your BulkClix API key.
    :param group_id: Group UUID.
    :param name: New name for the group.
    :param group_icon: Optional new icon key.
    """
    data = {"name": name}
    if group_icon:
        data["group_icon"] = group_icon
    return await _call_api(api_key, "PATCH", f"/sms-api/contact/updateGroup/{group_id}", json_data=data)

@mcp.tool()
async def contacts_delete_group(
    *,
    api_key: Optional[str] = None,
    group_id: str
) -> Dict[str, Any]:
    """
    Delete a contact group.
    
    :param api_key: Your BulkClix API key.
    :param group_id: Group UUID to delete.
    """
    return await _call_api(api_key, "DELETE", f"/sms-api/contact/deleteGroup/{group_id}")

@mcp.tool()
async def contacts_list(
    *,
    api_key: Optional[str] = None,
    group_id: str
) -> Dict[str, Any]:
    """
    List all contacts inside a specific group.
    
    :param api_key: Your BulkClix API key.
    :param group_id: Group UUID.
    """
    return await _call_api(api_key, "GET", f"/sms-api/contact/getContacts/{group_id}")

@mcp.tool()
async def contacts_add(
    *,
    api_key: Optional[str] = None,
    first_name: str,
    last_name: str,
    phone_number: str,
    contact_group_id: str,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a single contact to a group.
    
    :param api_key: Your BulkClix API key.
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
    return await _call_api(api_key, "POST", "/sms-api/contact/addContact", json_data=data)

@mcp.tool()
async def contacts_add_bulk(
    *,
    api_key: Optional[str] = None,
    contact_group_id: str,
    contacts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add multiple contacts to a contact group.
    
    :param api_key: Your BulkClix API key.
    :param contact_group_id: UUID of the target group.
    :param contacts: A list of dicts, each with keys: first_name, last_name, phone_number, and optional email.
    """
    return await _call_api(
        api_key,
        "POST",
        "/sms-api/contact/addBulkContact",
        json_data={
            "contact_group_id": contact_group_id,
            "contacts": contacts
        }
    )

@mcp.tool()
async def contacts_update(
    *,
    api_key: Optional[str] = None,
    contact_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update contact details.
    
    :param api_key: Your BulkClix API key.
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
    return await _call_api(api_key, "PATCH", f"/sms-api/contact/updateContact/{contact_id}", json_data=data)

@mcp.tool()
async def contacts_delete(
    *,
    api_key: Optional[str] = None,
    contact_id: str
) -> Dict[str, Any]:
    """
    Delete a contact.
    
    :param api_key: Your BulkClix API key.
    :param contact_id: Contact UUID to delete.
    """
    return await _call_api(api_key, "DELETE", f"/sms-api/contact/deleteContact/{contact_id}")

# ==============================================================================
# ACCOUNT / WALLET TOOLS
# ==============================================================================

@mcp.tool()
async def account_wallet_balance(*,
    api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Check your BulkClix wallet balance.
    
    :param api_key: Your BulkClix API key.
    """
    return await _call_api(api_key, "GET", "/account/balance")


if __name__ == "__main__":
    import sys
    # If "sse" is passed as an argument, run as SSE server, else run as stdio (default)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "sse":
        print("Starting BulkClix MCP server on SSE transport (http://localhost:8000/sse)...", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")

