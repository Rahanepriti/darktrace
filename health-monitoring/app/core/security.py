"""Key providers and bearer-token helpers."""
from __future__ import annotations

import hmac
import json
from pathlib import Path

from app.core.config import Settings
from app.crypto.aes_gcm import CryptoError, KeyProvider, KeyRing, decode_key

_PLACEHOLDERS = {"", "CHANGE_ME"}


def _ring_from(keys_raw: dict, active: int) -> KeyRing:
    try:
        keys = {int(k): decode_key(v) for k, v in keys_raw.items()}
    except CryptoError:
        raise
    except (ValueError, TypeError, AttributeError):
        raise CryptoError("invalid key configuration") from None
    return KeyRing(keys=keys, active_version=active)


class EnvKeyProvider:
    """Dev/simple deployments: HEALTH_ENCRYPTION_KEY is the key for ACTIVE_KEY_VERSION."""

    def __init__(self, settings: Settings):
        self._s = settings

    def load(self) -> KeyRing:
        s = self._s
        if s.health_encryption_key.strip() in _PLACEHOLDERS:
            raise CryptoError("HEALTH_ENCRYPTION_KEY is not set")
        keys: dict = {}
        if s.health_encryption_keys_previous.strip():
            try:
                prev = json.loads(s.health_encryption_keys_previous)
                if not isinstance(prev, dict):
                    raise ValueError
            except ValueError:
                raise CryptoError("HEALTH_ENCRYPTION_KEYS_PREVIOUS must be a JSON object") from None
            keys.update(prev)
        keys[str(s.active_key_version)] = s.health_encryption_key
        return _ring_from(keys, s.active_key_version)


class FileKeyProvider:
    """Reads {"active_version": 2, "keys": {"1": "...", "2": "..."}} - ideal for a Vault Agent
    template or a mounted Kubernetes secret; re-read on every refresh (hot rotation)."""

    def __init__(self, path: str):
        self._path = Path(path)

    def load(self) -> KeyRing:
        try:
            doc = json.loads(self._path.read_text())
            return _ring_from(doc["keys"], int(doc["active_version"]))
        except CryptoError:
            raise
        except Exception:
            raise CryptoError("cannot read key file") from None


def build_key_provider(settings: Settings) -> KeyProvider:
    if settings.health_encryption_keys_file:
        return FileKeyProvider(settings.health_encryption_keys_file)
    return EnvKeyProvider(settings)


def verify_bearer(header: str | None, expected: str) -> bool:
    """Constant-time check of an `Authorization: Bearer <token>` header."""
    if expected.strip() in _PLACEHOLDERS or not header:
        return False
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return hmac.compare_digest(token.strip().encode(), expected.encode())
