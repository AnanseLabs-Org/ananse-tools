import os
import time
import secrets
from typing import Dict, Any
from pydantic import AnyUrl
from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    AuthorizationParams,
    AuthorizationCode,
    RefreshToken,
    AccessToken,
    OAuthToken,
    construct_redirect_uri,
    TokenError
)
from db import _get_db

class InMemoryOAuthProvider:
    def __init__(self):
        self._clients: Dict[str, OAuthClientInformationFull] = {}
        self._codes: Dict[str, AuthorizationCode] = {}
        self._refresh_tokens: Dict[str, RefreshToken] = {}
        self._access_tokens: Dict[str, AccessToken] = {}
        
        # Pre-register a default client for testing
        default_client = OAuthClientInformationFull(
            client_id="bulkclix-client",
            client_secret="bulkclix-secret",
            client_id_issued_at=int(time.time()),
            client_secret_expires_at=None,
            redirect_uris=[AnyUrl("https://tools.ananselabs.org/")],
            scope="mcp"
        )
        self._clients["bulkclix-client"] = default_client

        # Pre-register ChatGPT client
        chatgpt_client_id = os.environ.get("OAUTH_CLIENT_ID", "956e6617-10ac-4e28-995a-e31bfe80f577")
        chatgpt_client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "bulkclix-secret")
        chatgpt_client = OAuthClientInformationFull(
            client_id=chatgpt_client_id,
            client_secret=chatgpt_client_secret,
            client_id_issued_at=int(time.time()),
            client_secret_expires_at=None,
            redirect_uris=[
                AnyUrl("https://chatgpt.com/connector/oauth/DBK931HlDaKv"),
                AnyUrl("https://chatgpt.com/connector_platform_oauth_redirect")
            ],
            scope="mcp"
        )
        self._clients[chatgpt_client_id] = chatgpt_client

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # Check cache
        client = self._clients.get(client_id)
        if client:
            return client
        # Check MongoDB
        db = _get_db()
        if db is not None:
            doc = await db.oauth_clients.find_one({"client_id": client_id}, {"_id": 0})
            if doc:
                # Convert redirect_uris back to AnyUrl
                if "redirect_uris" in doc and doc["redirect_uris"]:
                    doc["redirect_uris"] = [AnyUrl(u) for u in doc["redirect_uris"]]
                client = OAuthClientInformationFull(**doc)
                self._clients[client_id] = client
                return client
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info = client_info.model_copy(update={
                "client_id": secrets.token_hex(8),
                "client_secret": secrets.token_hex(16),
                "client_id_issued_at": int(time.time()),
                "client_secret_expires_at": None,
                "scope": client_info.scope or "mcp"
            })
        else:
            if not client_info.scope:
                client_info = client_info.model_copy(update={"scope": "mcp"})
        self._clients[client_info.client_id] = client_info
        # Save to MongoDB
        db = _get_db()
        if db is not None:
            # Serialize for MongoDB (Pydantic model dump)
            data = client_info.model_dump()
            if "redirect_uris" in data and data["redirect_uris"]:
                data["redirect_uris"] = [str(u) for u in data["redirect_uris"]]
            await db.oauth_clients.update_one(
                {"client_id": client_info.client_id},
                {"$set": data},
                upsert=True
            )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        code = secrets.token_hex(16)
        auth_code = AuthorizationCode(
            code=code,
            scopes=params.scopes or ["mcp"],
            expires_at=time.time() + 600,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="user"
        )
        self._codes[code] = auth_code
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self._codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.client_id != client.client_id:
            raise TokenError("invalid_grant", "Client mismatch")
        if authorization_code.expires_at < time.time():
            raise TokenError("invalid_grant", "Authorization code expired")
            
        self._codes.pop(authorization_code.code, None)
        
        access_token_str = "at_" + secrets.token_hex(32)
        refresh_token_str = "rt_" + secrets.token_hex(32)
        
        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
            resource=authorization_code.resource,
            subject=authorization_code.subject,
            claims={"sub": authorization_code.subject, "iss": "https://tools.ananselabs.org"}
        )
        refresh_token = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 30 * 86400,
            subject=authorization_code.subject
        )
        
        self._access_tokens[access_token_str] = access_token
        self._refresh_tokens[refresh_token_str] = refresh_token
        
        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh_token_str
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return self._refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if refresh_token.client_id != client.client_id:
            raise TokenError("invalid_grant", "Client mismatch")
            
        self._refresh_tokens.pop(refresh_token.token, None)
        
        access_token_str = "at_" + secrets.token_hex(32)
        refresh_token_str = "rt_" + secrets.token_hex(32)
        
        requested_scopes = scopes if scopes else refresh_token.scopes
        
        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=requested_scopes,
            expires_at=int(time.time()) + 3600,
            resource=None,
            subject=refresh_token.subject,
            claims={"sub": refresh_token.subject, "iss": "https://tools.ananselabs.org"}
        )
        new_refresh_token = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=requested_scopes,
            expires_at=int(time.time()) + 30 * 86400,
            subject=refresh_token.subject
        )
        
        self._access_tokens[access_token_str] = access_token
        self._refresh_tokens[refresh_token_str] = new_refresh_token
        
        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(requested_scopes),
            refresh_token=refresh_token_str
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self._access_tokens.get(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._access_tokens.pop(token.token, None)
        self._refresh_tokens.pop(token.token, None)
