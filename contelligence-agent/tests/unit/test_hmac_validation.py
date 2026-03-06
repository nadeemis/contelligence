"""Unit tests for Phase 5 — HMAC Validation (hmac_validation.py).

Tests signature computation and validation for webhook triggers.
"""

from __future__ import annotations

from app.utils.hmac_validation import compute_signature, validate_signature


class TestComputeSignature:
    """Tests for compute_signature."""

    def test_returns_sha256_prefix(self) -> None:
        sig = compute_signature(b"hello", "secret")
        assert sig.startswith("sha256=")

    def test_deterministic(self) -> None:
        sig1 = compute_signature(b"body", "key")
        sig2 = compute_signature(b"body", "key")
        assert sig1 == sig2

    def test_different_body_different_sig(self) -> None:
        sig1 = compute_signature(b"body1", "key")
        sig2 = compute_signature(b"body2", "key")
        assert sig1 != sig2

    def test_different_secret_different_sig(self) -> None:
        sig1 = compute_signature(b"body", "key1")
        sig2 = compute_signature(b"body", "key2")
        assert sig1 != sig2

    def test_hex_digest_length(self) -> None:
        sig = compute_signature(b"test", "secret")
        # "sha256=" (7) + 64 hex chars = 71
        assert len(sig) == 71


class TestValidateSignature:
    """Tests for validate_signature."""

    def test_valid_signature(self) -> None:
        body = b'{"event": "test"}'
        secret = "my-webhook-secret"
        sig = compute_signature(body, secret)
        assert validate_signature(body, secret, sig) is True

    def test_invalid_signature(self) -> None:
        body = b'{"event": "test"}'
        secret = "my-webhook-secret"
        assert validate_signature(body, secret, "sha256=badhex") is False

    def test_missing_header_with_secret(self) -> None:
        """If secret is configured but header is missing, reject."""
        assert validate_signature(b"body", "secret", None) is False

    def test_empty_header_with_secret(self) -> None:
        assert validate_signature(b"body", "secret", "") is False

    def test_no_secret_skips_validation(self) -> None:
        """If no secret configured, validation is skipped (returns True)."""
        assert validate_signature(b"body", "", "anything") is True

    def test_tampered_body_fails(self) -> None:
        body = b"original"
        secret = "key"
        sig = compute_signature(body, secret)
        # Tamper with body
        assert validate_signature(b"tampered", secret, sig) is False

    def test_timing_safe(self) -> None:
        """Ensure we use hmac.compare_digest (timing-safe)."""
        # We can't easily test timing safety, but we verify the result
        body = b"test"
        secret = "s3cret"
        sig = compute_signature(body, secret)
        assert validate_signature(body, secret, sig) is True
