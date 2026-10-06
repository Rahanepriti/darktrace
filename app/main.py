from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from .crypto_utils import decrypt_json, EncryptionError
from .health_store import store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("cyart.health")
app = FastAPI(title="CyArt DarkTrace Health Service", version="1.0.0")
FRESHNESS_SECONDS = int(os.getenv("HEARTBEAT_FRESHNESS_SECONDS", "60"))
MAX_CLOCK_SKEW_SECONDS = int(os.getenv("MAX_HEARTBEAT_AGE_SECONDS", "300"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
db_engine = create_async_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None

class Heartbeat(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    status: Literal["healthy", "degraded", "down"]
    timestamp: datetime
    queue_depth: int = Field(ge=0)
    last_successful_fetch: datetime | None = None

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

async def database_health() -> dict:
    if not db_engine:
        # Local/demo mode: make the missing DB configuration explicit rather than fake healthy.
        return {"status": "degraded", "latency_ms": None, "detail": "DATABASE_URL not configured"}
    started = asyncio.get_running_loop().time()
    try:
        await asyncio.wait_for(_db_ping(), timeout=1.25)
        elapsed = round((asyncio.get_running_loop().time() - started) * 1000, 2)
        return {"status": "healthy", "latency_ms": elapsed}
    except Exception as exc:
        logger.warning("Database health check failed: %s", type(exc).__name__)
        return {"status": "unhealthy", "latency_ms": None}

async def _db_ping() -> None:
    async with db_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

async def crawler_health() -> dict:
    workers = await store.all()
    now = utcnow()
    if not workers:
        return {"status": "unhealthy", "last_heartbeat": None, "active_workers": 0, "queue_depth": 0}
    # Store TTL removes stale workers; still validate timestamps to protect against old/replayed data.
    valid = []
    for worker in workers:
        try:
            ts = datetime.fromisoformat(worker["timestamp"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts).total_seconds() <= FRESHNESS_SECONDS:
                valid.append((worker, ts))
        except (KeyError, ValueError, TypeError):
            continue
    if not valid:
        latest = max(workers, key=lambda x: x.get("timestamp", ""))
        return {"status": "degraded", "last_heartbeat": latest.get("timestamp"),
                "active_workers": 0, "queue_depth": sum(int(w.get("queue_depth", 0)) for w in workers)}
    last_worker, last_ts = max(valid, key=lambda pair: pair[1])
    states = {w["status"] for w, _ in valid}
    status = "healthy" if states == {"healthy"} else ("unhealthy" if "down" in states else "degraded")
    return {"status": status, "last_heartbeat": last_ts.isoformat().replace("+00:00", "Z"),
            "active_workers": len(valid), "queue_depth": sum(int(w.get("queue_depth", 0)) for w, _ in valid)}

@app.on_event("startup")
async def startup() -> None:
    await store.connect()

@app.on_event("shutdown")
async def shutdown() -> None:
    await store.close()
    if db_engine:
        await db_engine.dispose()

@app.get("/api/v1/health")
async def get_health() -> dict:
    db, crawler = await asyncio.gather(database_health(), crawler_health())
    components = {"database": db, "crawler": crawler}
    statuses = [db["status"], crawler["status"]]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif all(s == "healthy" for s in statuses):
        overall = "healthy"
    else:
        overall = "degraded"
    return {"status": overall, "checked_at": utcnow().isoformat().replace("+00:00", "Z"),
            "components": components}

@app.websocket("/api/v1/ws/health")
async def crawler_heartbeat(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            token = await websocket.receive_text()
            try:
                plaintext = decrypt_json(token)
                heartbeat = Heartbeat.model_validate_json(plaintext)
                timestamp = heartbeat.timestamp
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                age = (utcnow() - timestamp).total_seconds()
                if age > MAX_CLOCK_SKEW_SECONDS or age < -60:
                    await websocket.send_json({"accepted": False, "error": "stale_or_future_timestamp"})
                    continue
                record = heartbeat.model_dump(mode="json")
                record["timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
                await store.put(heartbeat.worker_id, record)
                await websocket.send_json({"accepted": True, "worker_id": heartbeat.worker_id})
            except (EncryptionError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                # Do not log token, plaintext, or key material.
                logger.warning("Rejected heartbeat (%s)", type(exc).__name__)
                try:
                    await websocket.send_json({"accepted": False, "error": "invalid_heartbeat"})
                except Exception:
                    break
            except Exception as exc:
                logger.error("Heartbeat processing failed (%s)", type(exc).__name__)
                try:
                    await websocket.send_json({"accepted": False, "error": "processing_error"})
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info("Crawler WebSocket disconnected")
