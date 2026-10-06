"""AES-256-GCM message encryption with key versioning.

Wire format (base64url, no padding):
    key_version (2 bytes, big-endian) || nonce (12 bytes) || ciphertext || GCM tag (16 bytes)
AAD = key_version bytes + a fixed context label, so the version and protocol are authenticated.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import struct
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
VERSION_SIZE = 2
_AAD_CONTEXT = b"cyart-darktrace-health-v1"
_MAX_TOKEN_CHARS = 64 * 1024


class CryptoError(Exception):
    """Any crypto failure. Messages are deliberately generic (no oracle for attackers)."""


def generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encode_key(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode()


def decode_key(value: str | bytes) -> bytes:
    """Parse a 256-bit key given as 64 hex chars or base64/base64url."""
    v = value.decode() if isinstance(value, bytes) else value
    v = v.strip()
    if len(v) == 64:
        try:
            raw = bytes.fromhex(v)
            if len(raw) == KEY_SIZE:
                return raw
        except ValueError:
            pass
    padded = v + "=" * (-len(v) % 4)
    for alt in (b"-_", b"+/"):
        try:
            raw = base64.b64decode(padded, altchars=alt, validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(raw) == KEY_SIZE:
            return raw
    raise CryptoError("encryption key must be exactly 32 bytes (256 bits), base64 or hex encoded")


@dataclass(frozen=True)
class KeyRing:
    keys: Mapping[int, bytes]
    active_version: int

    def __post_init__(self) -> None:
        if not self.keys:
            raise CryptoError("key ring is empty")
        for ver, key in self.keys.items():
            if not (1 <= ver <= 0xFFFF) or len(key) != KEY_SIZE:
                raise CryptoError("invalid key ring entry")
        if self.active_version not in self.keys:
            raise CryptoError("active key version is not present in the key ring")

    def __repr__(self) -> str:  # never print key material
        return f"KeyRing(versions={sorted(self.keys)}, active={self.active_version})"


@dataclass(frozen=True)
class Decrypted:
    plaintext: bytes
    key_version: int
    nonce: bytes


def encrypt(ring: KeyRing, plaintext: bytes, version: int | None = None) -> str:
    version = ring.active_version if version is None else version
    key = ring.keys.get(version)
    if key is None:
        raise CryptoError("unknown key version")
    header = struct.pack(">H", version)
    nonce = os.urandom(NONCE_SIZE)  # fresh CSPRNG nonce per message
    ct = AESGCM(key).encrypt(nonce, plaintext, header + _AAD_CONTEXT)  # ct includes the tag
    return base64.urlsafe_b64encode(header + nonce + ct).rstrip(b"=").decode()


def decrypt(ring: KeyRing, token: str) -> Decrypted:
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_CHARS:
        raise CryptoError("invalid message")
    try:
        blob = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise CryptoError("invalid message") from None
    if len(blob) < VERSION_SIZE + NONCE_SIZE + TAG_SIZE:
        raise CryptoError("invalid message")
    header = blob[:VERSION_SIZE]
    nonce = blob[VERSION_SIZE : VERSION_SIZE + NONCE_SIZE]
    ct = blob[VERSION_SIZE + NONCE_SIZE :]
    (version,) = struct.unpack(">H", header)
    key = ring.keys.get(version)
    if key is None:
        raise CryptoError("invalid message")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ct, header + _AAD_CONTEXT)
    except InvalidTag:
        raise CryptoError("invalid message") from None
    return Decrypted(plaintext=plaintext, key_version=version, nonce=nonce)


class KeyProvider(Protocol):
    """Source of key material. Implement this for Vault / KMS / cloud secret stores."""

    def load(self) -> KeyRing: ...


class CryptoService:
    """Encrypt/decrypt facade that periodically reloads the key ring from its provider.

    Reloading is what allows key rotation without redeploying the crawler: update the
    secret store, and the next refresh picks up the new key(s) / active version.
    """

    def __init__(self, provider: KeyProvider, refresh_seconds: float = 60, clock: Callable[[], float] = time.monotonic):
        self._provider = provider
        self._refresh = refresh_seconds
        self._clock = clock
        self._ring = provider.load()  # fail fast on bad configuration
        self._loaded_at = clock()

    def _current(self) -> KeyRing:
        if self._clock() - self._loaded_at >= self._refresh:
            self._loaded_at = self._clock()
            try:
                self._ring = self._provider.load()
            except Exception:  # keep serving with the previous ring
                from app.core.logging import get_logger, log_event

                log_event(get_logger("crypto"), logging.WARNING, "key reload failed; keeping previous key ring")
        return self._ring

    @property
    def active_version(self) -> int:
        return self._current().active_version

    @property
    def versions(self) -> list[int]:
        return sorted(self._current().keys)

    def encrypt(self, plaintext: bytes, version: int | None = None) -> str:
        return encrypt(self._current(), plaintext, version)

    def decrypt(self, token: str) -> Decrypted:
        return decrypt(self._current(), token)
