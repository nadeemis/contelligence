"""Unit tests for Phase 4 — Auth Middleware (get_current_user, require_role, dev mode)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.middleware import get_current_user, require_role
from app.auth.models import Role, User


def _make_request(auth_header: str | None = None) -> MagicMock:
    """Create a mock FastAPI Request."""
    request = MagicMock()
    if auth_header:
        request.headers = {"Authorization": auth_header}
    else:
        request.headers = {}
    return request


class TestGetCurrentUser:
    """Test the mandatory auth dependency."""

    @pytest.mark.asyncio
    async def test_dev_mode_returns_synthetic_admin(self) -> None:
        """When AUTH_ENABLED=false, returns synthetic admin."""
        request = _make_request()
        with patch("app.auth.middleware.settings") as mock_settings:
            mock_settings.AUTH_ENABLED = False
            user = await get_current_user(request)
            assert user.is_admin is True
            assert user.oid == "dev-user"

    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self) -> None:
        request = _make_request()
        with patch("app.auth.middleware.settings") as mock_settings:
            mock_settings.AUTH_ENABLED = True
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self) -> None:
        request = _make_request("Bearer invalid-token")
        with patch("app.auth.middleware.settings") as mock_settings:
            mock_settings.AUTH_ENABLED = True
            with patch("app.auth.middleware.validate_token") as mock_validate:
                from app.auth.models import TokenValidationResult
                mock_validate.return_value = TokenValidationResult(valid=False)
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(request)
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self) -> None:
        request = _make_request("Bearer good-token")
        user = User(oid="abc", name="Test User", roles=[Role.OPERATOR])
        with patch("app.auth.middleware.settings") as mock_settings:
            mock_settings.AUTH_ENABLED = True
            with patch("app.auth.middleware.validate_token") as mock_validate:
                from app.auth.models import TokenValidationResult
                mock_validate.return_value = TokenValidationResult(
                    valid=True, user=user,
                )
                result = await get_current_user(request)
                assert result.oid == "abc"
                assert result.is_operator is True

class TestRequireRole:
    """Test role-based access control."""

    @pytest.mark.asyncio
    async def test_admin_role_passes_for_admin(self) -> None:
        dep = require_role(Role.ADMIN)
        user = User(oid="u1", roles=[Role.ADMIN])
        # Should not raise
        result = await dep(user)
        assert result.oid == "u1"

    @pytest.mark.asyncio
    async def test_admin_role_rejects_operator(self) -> None:
        dep = require_role(Role.ADMIN)
        user = User(oid="u2", roles=[Role.OPERATOR])
        with pytest.raises(HTTPException) as exc_info:
            await dep(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_role_passes_for_viewer(self) -> None:
        dep = require_role(Role.VIEWER)
        user = User(oid="u3", roles=[Role.VIEWER])
        result = await dep(user)
        assert result.oid == "u3"
