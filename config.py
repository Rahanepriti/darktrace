"""
Single place for every env var this project reads.
"""
import os
from dotenv import load_dotenv

load_dotenv()

#Redis (heartbeat cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
HEARTBEAT_TTL_SECONDS = int(os.getenv("HEARTBEAT_TTL_SECONDS", "90"))
# If a crawler's last heartbeat is older than this, treat it as stale/down
# even if Redis hasn't expired the key yet.
HEARTBEAT_STALE_AFTER_SECONDS = int(os.getenv("HEARTBEAT_STALE_AFTER_SECONDS", "60"))

# Replay protection
# Reject any heartbeat whose own timestamp is older than this -- stops a captured message being replayed later.
REPLAY_WINDOW_SECONDS = int(os.getenv("REPLAY_WINDOW_SECONDS", "300"))  # 5 min

# --- AES key config (see crypto_utils.load_key_by_version / get_active_key) ---
# HEALTH_AES_KEY_V1=<64 hex chars>
# HEALTH_AES_KEY_ACTIVE_VERSION=v1

#Database (for GET /api/v1/health's DB check)
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_CHECK_TIMEOUT_SECONDS = float(os.getenv("DB_CHECK_TIMEOUT_SECONDS", "2.0"))

#WebSocket server
WS_HOST = os.getenv("WS_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("WS_PORT", "8001"))
