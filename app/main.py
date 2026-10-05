from app.api.health_ws import router as health_ws_router
from fastapi import FastAPI
from app.api.health import router as health_router

app = FastAPI(title="CyArt DarkTrace Health Monitoring Service")


app.include_router(health_ws_router)

app.include_router(health_router)



