from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.routes.auth import router as auth_router
from backend.routes.api import router as api_router
from backend.routes.heartbeat import router as heartbeat_router, start_watchdog

# Resolver rutas absolutas — funciona tanto en desarrollo como en .exe (PyInstaller)
if getattr(sys, "frozen", False):
    _BASE = Path(sys._MEIPASS)
else:
    _BASE = Path(__file__).resolve().parents[1]

app = FastAPI(title="Legos Front", version="1.0.0")

app.mount("/static", StaticFiles(directory=str(_BASE / "frontend" / "static")), name="static")
templates = Jinja2Templates(directory=str(_BASE / "frontend" / "templates"))

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(heartbeat_router)


@app.on_event("startup")
async def on_startup():
    start_watchdog()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")
