from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.crawler_health import (
    REPLAY_WINDOW_SECONDS,
    decrypt_message,
    store_heartbeat,
)


router = APIRouter()


@router.websocket("/api/v1/ws/health")
async def health_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            encrypted_message = await websocket.receive_text()

            try:
                message = decrypt_message(encrypted_message)

            except Exception:
                print("Invalid or tampered heartbeat rejected")
                continue

            timestamp = message.get("timestamp")

            if not timestamp:
                print("Heartbeat rejected: missing timestamp")
                continue

            try:
                heartbeat_time = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )

                heartbeat_age = (
                    datetime.now(timezone.utc) - heartbeat_time
                ).total_seconds()

            except Exception:
                print("Heartbeat rejected: invalid timestamp")
                continue

            if abs(heartbeat_age) > REPLAY_WINDOW_SECONDS:
                print("Heartbeat rejected: timestamp outside replay window")
                continue

            worker_id = message.get("worker_id")

            if worker_id:
                store_heartbeat(worker_id, message)

            print("Received heartbeat:", message)

    except WebSocketDisconnect:
        print("Crawler disconnected")
