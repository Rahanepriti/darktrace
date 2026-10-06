""" --- Shared AES-256-GCM encrypt/decrypt utility -- 
used by BOTH the API (decrypting incoming heartbeats) and the crawler-side client (encrypting
outgoing heartbeats). This is the one module both sides must agree on
byte-for-byte, so its interface is intentionally small and explicit.

Wire format produced by encrypt() / consumed by decrypt():
    [12-byte nonce][ciphertext][16-byte GCM auth tag]
AESGCM.encrypt() already appends the tag to the ciphertext, so we only
need to prepend our own random nonce ourselves and strip it back off
before decrypting.


- AES-256-GCM only (never CBC) -- GCM's auth tag means a tampered or
  corrupted message is REJECTED, not silently decrypted into garbage.
- A fresh random nonce per message is mandatory -- reusing a nonce under
  the same key breaks GCM's security guarantee entirely. secrets.token_bytes
  gives us a cryptographically secure random nonce each call.
- Keys are never hard-coded, never committed, never passed as a URL/query
  parameter. See load_key_by_version() below for how keys are loaded.
"""
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

NONCE_SIZE_BYTES = 12  # 96 bits -- the standard, recommended nonce size for GCM
KEY_SIZE_BYTES = 32    # 256 bits -- AES-256


class DecryptionError(Exception):
    """wrong key, corrupted bytes, tampered message whose auth tag doesn't match. 
    Callers (the WS handler) must catch this specifically and reject the message, never let it crash the connection."""
    pass


def generate_key() -> bytes:
    """Generates a new random 256-bit key. Used by whoever provisions
    keys into the secrets store -- not called during normal encrypt/decrypt."""
    return secrets.token_bytes(KEY_SIZE_BYTES)


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypts plaintext bytes with AES-256-GCM under the given key.
    Returns nonce + ciphertext + tag, all concatenated -- this combined
    blob is what actually gets sent over the WebSocket."""
    if len(key) != KEY_SIZE_BYTES:
        raise ValueError(f"key must be {KEY_SIZE_BYTES} bytes (256 bits), got {len(key)}")

    nonce = secrets.token_bytes(NONCE_SIZE_BYTES)  # fresh nonce EVERY call -- never reuse
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext_and_tag


def decrypt(blob: bytes, key: bytes) -> bytes:
    """Reverses encrypt(). Raises DecryptionError on ANY failure --
    wrong key, corrupted bytes, or a tampered auth tag. Never returns
    garbage; a failure here always means an exception, never a bad
    plaintext slipping through."""
    if len(key) != KEY_SIZE_BYTES:
        raise ValueError(f"key must be {KEY_SIZE_BYTES} bytes (256 bits), got {len(key)}")

    if len(blob) < NONCE_SIZE_BYTES:
        raise DecryptionError("message too short to contain a valid nonce")

    nonce = blob[:NONCE_SIZE_BYTES]
    ciphertext_and_tag = blob[NONCE_SIZE_BYTES:]

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=None)
    except InvalidTag:
        # This is the tamper-detection case the spec calls out explicitly --
        # a corrupted or maliciously modified message is rejected here,
        # never silently decrypted into garbage.
        raise DecryptionError("authentication failed -- message is corrupted or was tampered with")


def load_key_by_version(version: str) -> bytes:
    """Loads a specific key version, e.g. load_key_by_version("v1").
    Looks for an env var named HEALTH_AES_KEY_<VERSION> containing the
    key as hex (64 hex chars = 32 bytes)."""
    env_var = f"HEALTH_AES_KEY_{version.upper()}"
    hex_key = os.getenv(env_var)
    if not hex_key:
        raise RuntimeError(f"No key configured for version '{version}' (expected env var {env_var})")

    key = bytes.fromhex(hex_key)
    if len(key) != KEY_SIZE_BYTES:
        raise RuntimeError(f"Key '{version}' is {len(key)} bytes, expected {KEY_SIZE_BYTES}")
    return key


def get_active_key() -> tuple[str, bytes]:
    """Returns (version, key) for whichever key version is currently
    marked active. Rotating the key means changing HEALTH_AES_KEY_ACTIVE_VERSION
    to point at a newly-provisioned version -- no redeploy of the
    encrypt/decrypt code itself, exactly as the spec asks for."""
    active_version = os.getenv("HEALTH_AES_KEY_ACTIVE_VERSION", "v1")
    return active_version, load_key_by_version(active_version)
