"""Server-side heartbeat pipeline: decrypt -> parse -> validate -> replay check -> cache."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError

from app.cache.redis_cache import CacheUnavailable, HeartbeatCache
from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.crypto.aes_gcm import CryptoError, CryptoService
from app.schemas.health import Heartbeat

log = get_logger("heartbeat")


@dataclass(frozen=True)
class IngestResult:
    ok: bool
    reason: str | None = None  # short, generic code returned to the crawler
    worker_id: str | None = None


class HeartbeatProcessor:
    def __init__(self, crypto: CryptoService, cache: HeartbeatCache, settings: Settings):
        self._crypto = crypto
        self._cache = cache
        self._s = settings

    def _reject(self, reason: str, **fields) -> IngestResult:
        log_event(log, logging.WARNING, "heartbeat rejected", reason=reason, **fields)
        return IngestResult(ok=False, reason=reason)

    async def process(self, raw: str, peer: str | None = None) -> IngestResult:
        try:
            dec = self._crypto.decrypt(raw)
        except CryptoError:
            return self._reject("decrypt_failed", peer=peer)

        try:
            payload = json.loads(dec.plaintext)
        except (ValueError, UnicodeDecodeError):
            return self._reject("invalid_json", peer=peer)

        try:
            hb = Heartbeat.model_validate(payload)
        except ValidationError:
            return self._reject("invalid_schema", peer=peer)

        now = datetime.now(timezone.utc)
        age = (now - hb.timestamp).total_seconds()
        if age > self._s.heartbeat_max_age_seconds:
            return self._reject("stale_timestamp", worker_id=hb.worker_id, peer=peer)
        if age < -self._s.heartbeat_clock_skew_seconds:
            return self._reject("future_timestamp", worker_id=hb.worker_id, peer=peer)

        try:
            nonce_ttl = self._s.heartbeat_max_age_seconds + self._s.heartbeat_clock_skew_seconds + 5
            if not await self._cache.claim_nonce(dec.nonce.hex(), nonce_ttl):
                return self._reject("replay", worker_id=hb.worker_id, peer=peer)
            await self._cache.store(hb, now)
        except CacheUnavailable as exc:
            log_event(log, logging.ERROR, "redis failure", reason=str(exc))
            return IngestResult(ok=False, reason="cache_unavailable")

        log_event(log, logging.INFO, "heartbeat received", worker_id=hb.worker_id, status=hb.status.value,
                  queue_depth=hb.queue_depth, key_version=dec.key_version)
        return IngestResult(ok=True, worker_id=hb.worker_id)
