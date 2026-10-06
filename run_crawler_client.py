from __future__ import annotations

import asyncio

from health_service import config
from health_service.crawler_client.heartbeat_client import run_heartbeat_client
from health_service.secrets import EnvSecretProvider


def main() -> None:
    provider = EnvSecretProvider(
        env_prefix=config.AES_KEY_ENV_PREFIX,
        active_version_env=config.ACTIVE_AES_KEY_VERSION_ENV,
        default_version=config.DEFAULT_AES_KEY_VERSION,
    )
    active_version = provider.get_active_version()
    key = provider.get_key(active_version)
    if key is None:
        raise SystemExit(
            f"No AES key configured for active version '{active_version}'. "
            f"Set {config.AES_KEY_ENV_PREFIX}{active_version.upper()} (base64-encoded 32-byte key)."
        )

    asyncio.run(
        run_heartbeat_client(
            websocket_url=config.WEBSOCKET_URL,
            worker_id=config.CRAWLER_WORKER_ID,
            key=key,
            key_version=active_version,
            interval_seconds=config.HEARTBEAT_INTERVAL_SECONDS,
            reconnect_backoff_seconds=config.CRAWLER_RECONNECT_BACKOFF_SECONDS,
        )
    )


if __name__ == "__main__":
    main()
