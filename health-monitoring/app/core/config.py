"""Application settings (environment / .env driven). No secrets have defaults."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # --- infrastructure -------------------------------------------------
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # --- encryption / key management -------------------------------------
    health_encryption_key: str = ""            # key for ACTIVE_KEY_VERSION (base64 or hex, 32 bytes)
    health_encryption_keys_previous: str = ""  # optional JSON {"1": "<key>"} - old versions kept for decrypt
    health_encryption_keys_file: str = ""      # optional JSON key file (Vault agent / k8s secret mount)
    active_key_version: int = Field(1, ge=1, le=65535)
    key_refresh_seconds: int = Field(60, ge=1)

    # --- heartbeat --------------------------------------------------------
    heartbeat_interval_seconds: int = Field(20, ge=1)
    heartbeat_ttl_seconds: int | None = Field(None, ge=1)  # default: 2 x interval
    heartbeat_max_age_seconds: int = Field(300, ge=1)      # replay window
    heartbeat_clock_skew_seconds: int = Field(30, ge=0)
    crawler_unhealthy_after_seconds: int = Field(300, ge=1)  # stale this long => unhealthy
    crawler_forget_after_seconds: int = Field(3600, ge=60)   # drop long-gone workers

    # --- timeouts ---------------------------------------------------------
    database_timeout_seconds: float = Field(1.0, gt=0)
    database_degraded_latency_ms: int = Field(500, ge=1)
    redis_timeout_seconds: float = Field(1.0, gt=0)
    health_budget_seconds: float = Field(1.8, gt=0)

    # --- access control ---------------------------------------------------
    public_health_endpoint: bool = False
    health_api_token: str = ""   # Bearer token: detailed /health + /ws/monitor
    crawler_ws_token: str = ""   # Bearer token: crawler -> /ws/health

    # --- websocket --------------------------------------------------------
    ws_max_message_bytes: int = Field(4096, ge=256)
    ws_idle_timeout_seconds: int = Field(90, ge=5)
    ws_max_consecutive_rejects: int = Field(5, ge=1)

    # --- real-time monitor ------------------------------------------------
    monitor_enabled: bool = True
    monitor_push_interval_seconds: float = Field(3.0, ge=0.5)
    monitor_max_connections: int = Field(20, ge=1)

    # --- crawler client ---------------------------------------------------
    health_ws_url: str = "ws://localhost:8000/api/v1/ws/health"
    worker_id: str = "cw-1"

    @property
    def heartbeat_ttl(self) -> int:
        return self.heartbeat_ttl_seconds or 2 * self.heartbeat_interval_seconds

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.heartbeat_ttl < self.heartbeat_interval_seconds:
            raise ValueError("HEARTBEAT_TTL_SECONDS must be >= HEARTBEAT_INTERVAL_SECONDS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
