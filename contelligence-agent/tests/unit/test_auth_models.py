"""Unit tests for Phase 4 — RBAC models and auth helpers."""

from __future__ import annotations

import pytest

from app.auth.models import Role, TokenValidationResult, User


class TestUserModel:
    """Test the User model and role checks."""

    def test_admin_role(self) -> None:
        u = User(oid="123", roles=[Role.ADMIN])
        assert u.is_admin is True
        assert u.is_operator is True  # admin implies operator

    def test_operator_role(self) -> None:
        u = User(oid="456", roles=[Role.OPERATOR])
        assert u.is_admin is False
        assert u.is_operator is True

    def test_viewer_role(self) -> None:
        u = User(oid="789", roles=[Role.VIEWER])
        assert u.is_admin is False
        assert u.is_operator is False

    def test_no_roles(self) -> None:
        u = User(oid="000")
        assert u.roles == []
        assert u.is_admin is False
        assert u.is_operator is False


class TestTokenValidationResult:
    """Test the validation result model."""

    def test_invalid_by_default(self) -> None:
        r = TokenValidationResult()
        assert r.valid is False
        assert r.user is None

    def test_valid_with_user(self) -> None:
        u = User(oid="abc", name="Test")
        r = TokenValidationResult(valid=True, user=u)
        assert r.valid is True
        assert r.user is not None
        assert r.user.oid == "abc"
