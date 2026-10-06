from fastapi import FastAPI, WebSocket

from app.health import get_health
from app.websocket import crawler_health_websocket

app = FastAPI(
    title="CyArt DarkTrace Health Monitoring Service",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "service": "CyArt DarkTrace Health Monitoring Service",
        "status": "running",
    }


@app.get("/api/v1/health")
async def health():
    return await get_health()


@app.websocket("/api/v1/ws/health")
async def health_websocket(websocket: WebSocket):
    await crawler_health_websocket(websocket)
