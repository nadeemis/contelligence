"""HMAC Validation — verify webhook request signatures.

Webhook triggers include an optional ``webhook_secret`` that is used
to compute an HMAC-SHA256 signature over the request body.  The caller
must include the signature in the ``X-Webhook-Signature`` header.

Signature format: ``sha256=<hex-digest>``
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger("contelligence-agent.hmac")


def compute_signature(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a request body.

    Returns the signature in the format ``sha256=<hex-digest>``.
    """
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def validate_signature(
    body: bytes,
    secret: str,
    header_value: str | None,
) -> bool:
    """Validate an HMAC-SHA256 signature from a webhook request header.

    Parameters
    ----------
    body:
        The raw request body bytes.
    secret:
        The shared webhook secret.
    header_value:
        The value of the ``X-Webhook-Signature`` header.

    Returns ``True`` if the signature is valid, ``False`` otherwise.
    If no secret is configured, returns ``True`` (validation skipped).
    """
    if not secret:
        # No secret configured — skip validation
        return True

    if not header_value:
        logger.warning("Missing X-Webhook-Signature header.")
        return False

    expected = compute_signature(body, secret)
    valid = hmac.compare_digest(expected, header_value)

    if not valid:
        logger.warning("HMAC signature mismatch.")

    return valid
