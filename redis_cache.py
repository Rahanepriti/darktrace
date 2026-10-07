# Thin wrapper around Redis for storing/reading each crawler's last known status. 
# WS server WRITES here on every valid heartbeat; the /api/v1/health endpoint READS here 
 
import json
import time

import redis

from config import REDIS_URL, HEARTBEAT_TTL_SECONDS

_redis_client = redis.from_url(REDIS_URL, decode_responses=True)

CRAWLER_STATUS_KEY_PREFIX = "health:crawler_status:"
CRAWLER_IDS_SET_KEY = "health:known_crawler_ids"


def _key_for(crawler_id: str) -> str:
    return f"{CRAWLER_STATUS_KEY_PREFIX}{crawler_id}"


def set_crawler_status(crawler_id: str, status: str, reported_ts: float) -> None:
    """Called by the WS server after a heartbeat passes decryption,
    schema validation, and replay checks. Stores the status plus the
    time WE received it (received_at) separately from the time the
    crawler claims it sent it (reported_ts) -- useful for debugging
    clock drift between machines."""
    payload = {
        "status": status,
        "reported_ts": reported_ts,
        "received_at": time.time(),
    }
    _redis_client.set(_key_for(crawler_id), json.dumps(payload), ex=HEARTBEAT_TTL_SECONDS)
    _redis_client.sadd(CRAWLER_IDS_SET_KEY, crawler_id)


def get_crawler_status(crawler_id: str) -> dict | None:
    """Returns the stored status dict, or None if the key expired/never
    existed -- which the caller should treat as 'crawler not reporting'."""
    raw = _redis_client.get(_key_for(crawler_id))
    if raw is None:
        return None
    return json.loads(raw)


def get_all_crawler_statuses() -> dict:
    """Returns {crawler_id: status_dict_or_None} for every crawler we've
    ever seen a heartbeat from. A None value means that crawler's key
    has expired -- it's gone quiet."""
    crawler_ids = _redis_client.smembers(CRAWLER_IDS_SET_KEY)
    result = {}
    for crawler_id in crawler_ids:
        result[crawler_id] = get_crawler_status(crawler_id)
    return result
