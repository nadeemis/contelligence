"""FastAPI middleware / dependencies for RBAC enforcement.

Provides ``get_current_user`` (mandatory auth) and
``get_optional_user`` (soft auth) dependencies, plus a
``require_role(role)`` dependency factory.
"""

from __future__ import annotations

import getpass
import logging
import os
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.dependencies import get_settings
from app.settings import AppSettings

from .helpers import validate_token
from .models import Role, User

logger = logging.getLogger(f"contelligence-agent.{__name__}")

def _extract_bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _get_local_os_user() -> User:
    """Build a User from the local OS account details."""
    username = getpass.getuser()
    uid = username if username else (str(os.getuid()) if hasattr(os, "getuid") else "unknown")
    return User(
        oid=f"local-{uid}",
        name=username,
        email=f"{username}@localhost",
        roles=[Role.ADMIN],
        tenant_id="local",
    )


async def get_current_user(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> User:
    """FastAPI dependency — returns validated ``User`` or raises 401.

    When ``STORAGE_MODE`` is ``"local"``, returns a user derived from the
    local OS account.  When ``AUTH_ENABLED`` is ``False`` (dev mode),
    returns a synthetic admin user.
    """
    if settings.STORAGE_MODE == "local":
        return _get_local_os_user()

    if not settings.AUTH_ENABLED:
        return User(
            oid="dev-user",
            name="Developer",
            email="dev@local",
            roles=[Role.ADMIN],
            tenant_id="dev",
        )

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await validate_token(
        token,
        tenant_id=settings.AZURE_AD_TENANT_ID,
        client_id=settings.AZURE_AD_CLIENT_ID,
    )

    if not result.valid or result.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result.user

def require_role(role: Role) -> Any:
    """Dependency factory — ensures the caller has a specific role."""

    async def _check_role(user: User = Depends(get_current_user)) -> User:
        if role == Role.ADMIN and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role.value}' required",
            )
        if role == Role.OPERATOR and not user.is_operator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role.value}' required",
            )
        return user

    return _check_role
