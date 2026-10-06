from __future__ import annotations

import base64
import json
import os
from typing import Callable, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE_BYTES = 12
KEY_SIZE_BYTES = 32

KeyResolver = Callable[[str], Optional[bytes]]


class DecryptionError(Exception):
    pass


class InvalidKeyError(Exception):
    pass


def _validate_key(key: bytes) -> None:
    if not isinstance(key, (bytes, bytearray)) or len(key) != KEY_SIZE_BYTES:
        raise InvalidKeyError(f"AES-256-GCM key must be exactly {KEY_SIZE_BYTES} bytes")


def encrypt_message(plaintext: bytes, key: bytes, key_version: str) -> str:
    _validate_key(key)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    aad = key_version.encode("utf-8")
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    envelope = {
        "key_version": key_version,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return json.dumps(envelope)


def decrypt_message(envelope_text: str, key_resolver: KeyResolver) -> bytes:
    try:
        envelope = json.loads(envelope_text)
        key_version = envelope["key_version"]
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DecryptionError("Malformed heartbeat envelope") from exc

    if len(nonce) != NONCE_SIZE_BYTES:
        raise DecryptionError("Malformed nonce length")

    key = key_resolver(key_version)
    if key is None:
        raise DecryptionError(f"Unknown or inactive key version: {key_version}")

    try:
        _validate_key(key)
    except InvalidKeyError as exc:
        raise DecryptionError(str(exc)) from exc

    aesgcm = AESGCM(key)
    aad = key_version.encode("utf-8")
    try:
        return aesgcm.decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise DecryptionError("Authentication tag verification failed") from exc
