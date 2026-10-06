"""AES-256-GCM helpers for encrypted crawler heartbeats."""
from __future__ import annotations
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12
KEY_SIZE = 32

class EncryptionError(ValueError):
    """Raised when an encrypted heartbeat cannot be authenticated/decrypted."""

def load_key() -> bytes:
    """Load a 32-byte key from HEALTH_SHARED_KEY_B64; never hard-code secrets."""
    value = os.getenv("HEALTH_SHARED_KEY_B64", "").strip()
    if not value:
        raise RuntimeError(
            "HEALTH_SHARED_KEY_B64 is missing. Generate one with: "
            "python -c 'import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())'"
        )
    try:
        key = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RuntimeError("HEALTH_SHARED_KEY_B64 must be valid Base64.") from exc
    if len(key) != KEY_SIZE:
        raise RuntimeError("HEALTH_SHARED_KEY_B64 must decode to exactly 32 bytes (AES-256).")
    return key

def encrypt_json(plaintext: bytes, key: bytes | None = None) -> str:
    """Return Base64(nonce || AES-GCM ciphertext+tag). A fresh nonce is used per message."""
    key = key or load_key()
    if len(key) != KEY_SIZE:
        raise ValueError("AES-256-GCM requires a 32-byte key.")
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")

def decrypt_json(token: str, key: bytes | None = None) -> bytes:
    """Authenticate and decrypt Base64(nonce || ciphertext+tag)."""
    key = key or load_key()
    if len(key) != KEY_SIZE:
        raise ValueError("AES-256-GCM requires a 32-byte key.")
    try:
        raw = base64.b64decode(token, validate=True)
        if len(raw) < NONCE_SIZE + 16:
            raise ValueError("Encrypted message is too short.")
        return AESGCM(key).decrypt(raw[:NONCE_SIZE], raw[NONCE_SIZE:], None)
    except Exception as exc:
        raise EncryptionError("Heartbeat authentication/decryption failed.") from exc
