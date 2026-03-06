"""JWT validation helpers for Azure AD / Entra ID tokens.

Fetches the OpenID Connect configuration and JWKS from the Azure AD
well-known endpoint, then validates incoming ``Authorization: Bearer``
tokens.  The validated user is cached per-request using FastAPI
``Depends()``.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import httpx
from jose import JWTError, jwt

from .models import Role, TokenValidationResult, User

logger = logging.getLogger(f"contelligence-agent.{__name__}")

_OPENID_CONFIG_URL_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
)

# Module-level caches (populated on first use)
_jwks: dict[str, Any] | None = None
_issuer: str | None = None


async def _fetch_openid_metadata(tenant_id: str) -> tuple[dict[str, Any], str]:
    """Fetch JWKS and issuer from the Azure AD OpenID configuration."""
    global _jwks, _issuer  # noqa: PLW0603  — intentional module-level cache

    if _jwks is not None and _issuer is not None:
        return _jwks, _issuer

    config_url = _OPENID_CONFIG_URL_TEMPLATE.format(tenant_id=tenant_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(config_url)
        resp.raise_for_status()
        config = resp.json()

        jwks_resp = await client.get(config["jwks_uri"])
        jwks_resp.raise_for_status()
        _jwks = jwks_resp.json()
        _issuer = config["issuer"]

    return _jwks, _issuer


def _extract_roles(claims: dict[str, Any]) -> list[Role]:
    """Extract app roles from JWT claims."""
    raw_roles = claims.get("roles", [])
    result: list[Role] = []
    for r in raw_roles:
        try:
            result.append(Role(r.lower()))
        except ValueError:
            logger.debug("Ignoring unknown role: %s", r)
    return result


async def validate_token(
    token: str,
    *,
    tenant_id: str,
    client_id: str,
) -> TokenValidationResult:
    """Validate an Azure AD JWT and return the user.

    Parameters
    ----------
    token : str
        Raw JWT from the ``Authorization: Bearer`` header.
    tenant_id : str
        Expected Azure AD tenant.
    client_id : str
        Expected audience (app registration client ID).
    """
    try:
        jwks, issuer = await _fetch_openid_metadata(tenant_id)

        # Decode the JWT header to find the matching key
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        rsa_key: dict[str, Any] = {}
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            return TokenValidationResult(
                valid=False, error="No matching signing key found"
            )

        claims = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
        )

        user = User(
            oid=claims.get("oid", claims.get("sub", "")),
            name=claims.get("name", ""),
            email=claims.get("preferred_username", claims.get("email", "")),
            roles=_extract_roles(claims),
            tenant_id=claims.get("tid", tenant_id),
        )
        return TokenValidationResult(valid=True, user=user)

    except JWTError as e:
        logger.warning("JWT validation failed: %s", e)
        return TokenValidationResult(valid=False, error=str(e))
    except Exception as e:
        logger.exception("Unexpected error during token validation")
        return TokenValidationResult(valid=False, error=str(e))


def reset_openid_cache() -> None:
    """Clear cached JWKS and issuer (useful in tests)."""
    global _jwks, _issuer  # noqa: PLW0603
    _jwks = None
    _issuer = None
