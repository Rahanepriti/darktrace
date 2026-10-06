"""Serves the self-contained real-time dashboard (no external assets, strict CSP)."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.container import get_container

router = APIRouter(tags=["dashboard"])
_HTML = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"
_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; base-uri 'none'; frame-ancestors 'none'")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    if not get_container(request).settings.monitor_enabled:
        raise HTTPException(404)
    return HTMLResponse(_HTML.read_text(encoding="utf-8"),
                        headers={"Content-Security-Policy": _CSP, "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})
