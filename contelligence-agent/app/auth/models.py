"""Auth models for RBAC and session isolation.

Defines the ``User`` model returned after JWT validation and
the ``TokenValidationResult`` model for middleware chaining.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Built-in roles for the HikmaForge agent."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(BaseModel):
    """Authenticated user extracted from the JWT.

    ``oid`` is the Azure AD object ID and serves as the canonical user
    identifier.  ``roles`` come from AAD app-role assignments.
    """

    oid: str = Field(..., description="Azure AD object ID")
    name: str = Field(default="", description="Display name")
    email: str = Field(default="", description="UPN / email")
    roles: list[Role] = Field(default_factory=list)
    tenant_id: str = Field(default="", description="Azure AD tenant ID")

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles

    @property
    def is_operator(self) -> bool:
        return Role.OPERATOR in self.roles or self.is_admin


class TokenValidationResult(BaseModel):
    """Result of JWT token validation."""

    valid: bool = False
    user: User | None = None
    error: str | None = None
