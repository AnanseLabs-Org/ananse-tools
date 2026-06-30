import logging
import jwt
from mcp.server.auth.provider import TokenVerifier, AccessToken

logger = logging.getLogger(__name__)

class Auth0TokenVerifier(TokenVerifier):
    def __init__(self, domain: str, audience: str):
        self.domain = domain  # e.g., "dev-0rvyw5vo8eu0rdbp.uk.auth0.com"
        self.audience = audience
        self.jwks_url = f"https://{domain}/.well-known/jwks.json"
        self.jwks_client = jwt.PyJWKClient(self.jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=f"https://{self.domain}/"
            )
            
            # Auth0 scopes are typically space-separated strings in the "scope" claim
            scopes_raw = payload.get("scope", "")
            scopes = scopes_raw.split() if isinstance(scopes_raw, str) else list(scopes_raw)
            
            return AccessToken(
                token=token,
                client_id=payload.get("azp", "unknown"),
                scopes=scopes,
                expires_at=payload.get("exp"),
                subject=payload.get("sub"),
                claims=payload
            )
        except Exception as e:
            logger.warning(f"Auth0 token validation failed: {e}")
            return None
