import json
import os
from datetime import datetime, timezone
import redis
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

load_dotenv()

#replay protection
REPLAY_WINDOW_SECONDS = 300

redis_client = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True,
)


ENCRYPTION_KEY = os.getenv("HEALTH_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise RuntimeError("HEALTH_ENCRYPTION_KEY is not configured")

if len(ENCRYPTION_KEY) != 64:
    raise RuntimeError("HEALTH_ENCRYPTION_KEY must be 64 hexadecimal characters")

try:
    encryption_key = bytes.fromhex(ENCRYPTION_KEY)
except ValueError:
    raise RuntimeError("HEALTH_ENCRYPTION_KEY must contain only hexadecimal characters")

aesgcm = AESGCM(encryption_key)


def encrypt_message(message: dict) -> str:
    nonce = os.urandom(12)

    plaintext = json.dumps(message).encode("utf-8")

    ciphertext = aesgcm.encrypt(
        nonce,
        plaintext,
        None,
    )

    return (
        nonce.hex()
        + ":"
        + ciphertext.hex()
    )


def decrypt_message(encrypted_message: str) -> dict:
    nonce_hex, ciphertext_hex = encrypted_message.split(":", 1)

    nonce = bytes.fromhex(nonce_hex)
    ciphertext = bytes.fromhex(ciphertext_hex)

    plaintext = aesgcm.decrypt(
        nonce,
        ciphertext,
        None,
    )

    return json.loads(plaintext.decode("utf-8"))


def store_heartbeat(worker_id: str, heartbeat: dict, ttl: int = 60):
    key = f"crawler:health:{worker_id}"

    redis_client.set(
        key,
        json.dumps(heartbeat),
        ex=ttl,
    )


def get_heartbeat(worker_id: str):
    key = f"crawler:health:{worker_id}"

    data = redis_client.get(key)

    if data is None:
        return None

    return json.loads(data)
    
    
def get_all_heartbeats():
    heartbeats = []

    for key in redis_client.scan_iter(match="crawler:health:*"):
        data = redis_client.get(key)

        if data is not None:
            heartbeats.append(json.loads(data))

    return heartbeats


def check_crawler_health():
    heartbeats = get_all_heartbeats()

    if not heartbeats:
        return {
            "status": "degraded",
            "last_heartbeat": None,
            "active_workers": 0,
            "queue_depth": 0,
        }

    now = datetime.now(timezone.utc)

    active_workers = 0
    total_queue_depth = 0
    latest_heartbeat = None
    overall_status = "healthy"

    for heartbeat in heartbeats:
        try:
            heartbeat_time = datetime.fromisoformat(
                heartbeat["timestamp"].replace("Z", "+00:00")
            )

            heartbeat_age = (
                now - heartbeat_time
            ).total_seconds()

        except Exception:
            overall_status = "degraded"
            continue

        if heartbeat_age <= 60:
            active_workers += 1
            total_queue_depth += heartbeat.get("queue_depth", 0)

            if latest_heartbeat is None or heartbeat["timestamp"] > latest_heartbeat:
                latest_heartbeat = heartbeat["timestamp"]

            if heartbeat.get("status") != "healthy":
                overall_status = "degraded"

        else:
            overall_status = "degraded"

    if active_workers == 0:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "last_heartbeat": latest_heartbeat,
        "active_workers": active_workers,
        "queue_depth": total_queue_depth,
    }
