from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Tuple

SIGNATURE_HEADER = "X-Notify-Signature"
TIMESTAMP_HEADER = "X-Notify-Timestamp"
_DEFAULT_TOLERANCE_SECONDS = 300


def sign_payload(secret: str, body: bytes, *, timestamp: int | None = None) -> Tuple[str, str]:
    """Create a timestamped HMAC signature for the given payload.

    Args:
        secret: Shared signing secret for the destination.
        body: Raw request body bytes as they will be sent over the wire.
        timestamp: Optional epoch timestamp to use. Defaults to current time.

    Returns:
        A tuple of (timestamp, signature) where timestamp is a string epoch
        seconds value and signature is a base64 encoded HMAC-SHA256 digest.
    """

    if not secret:
        raise ValueError("Secret must be provided for signing")
    ts = str(int(timestamp or time.time()))
    message = ts.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("utf-8")
    return ts, signature


def build_signature_headers(secret: str, body: bytes, *, timestamp: int | None = None) -> dict[str, str]:
    """Produce signature headers for an outbound webhook payload."""

    ts, signature = sign_payload(secret, body, timestamp=timestamp)
    return {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: signature,
    }


def verify_signature(
    secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
    *,
    tolerance_seconds: int = _DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """Verify an inbound webhook signature.

    Args:
        secret: Shared secret used for signing.
        body: Raw request body bytes exactly as received.
        timestamp: Timestamp string received in the header.
        signature: Base64 signature received in the header.
        tolerance_seconds: Permitted clock skew in seconds (default: 5 minutes).

    Returns:
        True if the signature is valid and within the tolerated timestamp window.
    """

    if not secret or not timestamp or not signature:
        return False

    try:
        ts_int = int(timestamp)
    except ValueError:
        return False

    if tolerance_seconds >= 0:
        current = int(time.time())
        if abs(current - ts_int) > tolerance_seconds:
            return False

    expected_ts, expected_signature = sign_payload(secret, body, timestamp=ts_int)
    if expected_ts != timestamp:
        return False
    return hmac.compare_digest(expected_signature, signature)


__all__ = [
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "build_signature_headers",
    "sign_payload",
    "verify_signature",
]
