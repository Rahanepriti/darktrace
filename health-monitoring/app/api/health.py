"""GET /api/v1/health"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.container import get_container
from app.core.security import verify_bearer
from app.schemas.health import DetailedHealthResponse, HealthStatus, PublicHealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get(
    "/health",
    response_model=DetailedHealthResponse | PublicHealthResponse,
    response_model_exclude_none=True,
    responses={401: {"description": "Authentication required"}, 503: {"description": "Unhealthy"}},
)
async def get_health(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    """Authenticated callers (Bearer HEALTH_API_TOKEN) get component detail.
    Unauthenticated callers get `{"status": ...}` only if PUBLIC_HEALTH_ENDPOINT=true, else 401."""
    c = get_container(request)
    authed = False
    if authorization is not None:
        if not verify_bearer(authorization, c.settings.health_api_token):
            raise HTTPException(status_code=401, detail="invalid credentials", headers={"WWW-Authenticate": "Bearer"})
        authed = True
    elif not c.settings.public_health_endpoint:
        raise HTTPException(status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Bearer"})

    report = await c.health_service.check()
    body = (
        report.model_dump(mode="json", exclude_none=True)
        if authed
        else PublicHealthResponse(status=report.status).model_dump(mode="json")
    )
    code = 503 if report.status == HealthStatus.unhealthy else 200
    return JSONResponse(body, status_code=code, headers={"Cache-Control": "no-store"})
