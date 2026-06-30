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
            redirect_uris=[AnyUrl("https://tools.ananselabs.org/")]
        )
        self._clients["bulkclix-client"] = default_client

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info = OAuthClientInformationFull(
                client_id=secrets.token_hex(8),
                client_secret=secrets.token_hex(16),
                client_id_issued_at=int(time.time()),
                client_secret_expires_at=None,
                redirect_uris=client_info.redirect_uris
            )
        self._clients[client_info.client_id] = client_info

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
