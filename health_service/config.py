from __future__ import annotations

import os


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_DSN: str = _env_str(
    "HEALTH_DATABASE_DSN", "postgresql://darktrace:darktrace@localhost:5432/darktrace"
)
DATABASE_CHECK_TIMEOUT_SECONDS: float = _env_float("HEALTH_DATABASE_CHECK_TIMEOUT_SECONDS", 1.5)

REDIS_URL: str = _env_str("HEALTH_REDIS_URL", "redis://localhost:6379/2")
HEARTBEAT_CACHE_KEY_PREFIX: str = _env_str("HEALTH_HEARTBEAT_CACHE_KEY_PREFIX", "health:crawler:heartbeat:")

HEARTBEAT_INTERVAL_SECONDS: int = _env_int("HEALTH_HEARTBEAT_INTERVAL_SECONDS", 20)
HEARTBEAT_TTL_MULTIPLIER: int = _env_int("HEALTH_HEARTBEAT_TTL_MULTIPLIER", 2)
HEARTBEAT_TTL_SECONDS: int = HEARTBEAT_INTERVAL_SECONDS * HEARTBEAT_TTL_MULTIPLIER
HEARTBEAT_FRESHNESS_SECONDS: int = _env_int(
    "HEALTH_HEARTBEAT_FRESHNESS_SECONDS", int(HEARTBEAT_INTERVAL_SECONDS * 1.5)
)

REPLAY_WINDOW_SECONDS: int = _env_int("HEALTH_REPLAY_WINDOW_SECONDS", 300)

AES_KEY_ENV_PREFIX: str = _env_str("HEALTH_AES_KEY_ENV_PREFIX", "AES_KEY_")
ACTIVE_AES_KEY_VERSION_ENV: str = _env_str("HEALTH_ACTIVE_AES_KEY_VERSION_ENV", "ACTIVE_AES_KEY_VERSION")
DEFAULT_AES_KEY_VERSION: str = _env_str("HEALTH_DEFAULT_AES_KEY_VERSION", "v1")

HEALTH_DETAILED_REQUIRES_AUTH: bool = _env_bool("HEALTH_DETAILED_REQUIRES_AUTH", False)
HEALTH_API_KEY: str = _env_str("HEALTH_API_KEY", "")

RESPONSE_LATENCY_BUDGET_SECONDS: float = _env_float("HEALTH_RESPONSE_LATENCY_BUDGET_SECONDS", 2.0)

WEBSOCKET_URL: str = _env_str("HEALTH_WEBSOCKET_URL", "wss://localhost:8000/api/v1/ws/health")
CRAWLER_WORKER_ID: str = _env_str("HEALTH_CRAWLER_WORKER_ID", "cw-local")
CRAWLER_RECONNECT_BACKOFF_SECONDS: float = _env_float("HEALTH_CRAWLER_RECONNECT_BACKOFF_SECONDS", 5.0)
