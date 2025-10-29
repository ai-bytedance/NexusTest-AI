from __future__ import annotations

import base64
import binascii
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class SecretEncryptionError(RuntimeError):
    """Raised when secret encryption or decryption fails."""


_KEY_CACHE: tuple[str, bytes] | None = None


def clear_secret_key_cache() -> None:
    global _KEY_CACHE
    _KEY_CACHE = None


def _decode_key_material(raw_value: str) -> tuple[str, bytes]:
    raw_value = raw_value.strip()
    if not raw_value:
        raise SecretEncryptionError("SECRET_ENC_KEY is not configured")

    if ":" in raw_value:
        version, key_part = raw_value.split(":", 1)
        version = version or "v1"
    else:
        version = "v1"
        key_part = raw_value

    key_part = key_part.strip()
    key_bytes: bytes | None = None

    if not key_part:
        raise SecretEncryptionError("SECRET_ENC_KEY must include key material")

    if all(ch in "0123456789abcdefABCDEF" for ch in key_part) and len(key_part) in (32, 48, 64):
        try:
            key_bytes = bytes.fromhex(key_part)
        except ValueError as exc:  # pragma: no cover - defensive
            raise SecretEncryptionError("SECRET_ENC_KEY hex payload is invalid") from exc
    else:
        try:
            key_bytes = base64.urlsafe_b64decode(key_part)
        except (binascii.Error, ValueError):
            key_bytes = key_part.encode("utf-8")

    if len(key_bytes) not in (16, 24, 32):
        raise SecretEncryptionError("SECRET_ENC_KEY must decode to 16, 24, or 32 bytes for AES-GCM")

    return version, key_bytes


def _get_key_material() -> tuple[str, bytes]:
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    settings = get_settings()
    version, key_bytes = _decode_key_material(settings.secret_enc_key)
    _KEY_CACHE = (version, key_bytes)
    return _KEY_CACHE


def encrypt_secret_value(value: str) -> str:
    version, key_bytes = _get_key_material()
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), version.encode("utf-8"))
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")
    return f"{version}:{payload}"


def decrypt_secret_value(payload: str) -> str:
    stored_version: str
    encoded_payload: str
    if ":" in payload:
        stored_version, encoded_payload = payload.split(":", 1)
        stored_version = stored_version or "v1"
    else:
        stored_version = "v1"
        encoded_payload = payload

    version, key_bytes = _get_key_material()
    if stored_version != version:
        raise SecretEncryptionError("Secret key version mismatch")

    try:
        raw = base64.urlsafe_b64decode(encoded_payload)
    except (binascii.Error, ValueError) as exc:
        raise SecretEncryptionError("Encrypted secret payload is invalid") from exc

    if len(raw) < 13:
        raise SecretEncryptionError("Encrypted secret payload is too short")

    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key_bytes)
    try:
        decrypted = aesgcm.decrypt(nonce, ciphertext, version.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - cryptography raises multiple exceptions
        raise SecretEncryptionError("Failed to decrypt secret payload") from exc
    return decrypted.decode("utf-8")


def encrypt_secret_mapping(mapping: dict[str, Any] | None) -> dict[str, str]:
    if not mapping:
        return {}
    encrypted: dict[str, str] = {}
    for key, value in mapping.items():
        if value is None:
            continue
        encrypted[key] = encrypt_secret_value(str(value))
    return encrypted


def decrypt_secret_mapping(mapping: dict[str, Any] | None) -> dict[str, str]:
    if not mapping:
        return {}
    decrypted: dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or value is None:
            continue
        decrypted[key] = decrypt_secret_value(str(value))
    return decrypted


def mask_secret_mapping(mapping: dict[str, Any] | None, placeholder: str = "***") -> dict[str, str]:
    if not mapping:
        return {}
    return {key: placeholder for key in mapping.keys() if isinstance(key, str)}


__all__ = [
    "SecretEncryptionError",
    "clear_secret_key_cache",
    "encrypt_secret_value",
    "decrypt_secret_value",
    "encrypt_secret_mapping",
    "decrypt_secret_mapping",
    "mask_secret_mapping",
]
