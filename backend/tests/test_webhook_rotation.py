from __future__ import annotations

import json
from datetime import datetime

import hashlib
import hmac

from app.services.webhooks import WebhookService as WS


def test_webhook_secret_rotation_dual_valid_logic() -> None:
    # Before cutover, platform signs with old secret; receiver should verify with old
    payload = {"ping": True}
    payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    ts = int(datetime.utcnow().timestamp())
    sig_payload = f"{ts}.{payload_str}"

    old_secret = "old_secret"
    new_secret = "new_secret"

    # Sign with old secret
    signature_old = hmac.new(old_secret.encode(), sig_payload.encode(), hashlib.sha256).hexdigest()
    header_sig_old = f"sha256={signature_old}"

    assert WS.verify_signature(payload_str, header_sig_old, old_secret, ts) is True
    assert WS.verify_signature(payload_str, header_sig_old, new_secret, ts) is False

    # After cutover, sign with new secret; receiver should verify with new
    signature_new = hmac.new(new_secret.encode(), sig_payload.encode(), hashlib.sha256).hexdigest()
    header_sig_new = f"sha256={signature_new}"

    assert WS.verify_signature(payload_str, header_sig_new, new_secret, ts) is True
    assert WS.verify_signature(payload_str, header_sig_new, old_secret, ts) is False
