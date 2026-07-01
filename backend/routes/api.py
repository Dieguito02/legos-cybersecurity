from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.core.config import settings
from backend.core.security import verify_session_token
from backend.services import history_service
from backend.services.command_executor import (
    execute,
    cancel,
    get_log_queue,
    get_active_operations,
)
from backend.services.command_registry import get_all_commands, get_commands_by_category
from backend.services.network_service import get_network_status

router = APIRouter(prefix="/api", tags=["api"])


# ── Auth guard helper ─────────────────────────────────────────────────────────

def _get_user(request: Request) -> str | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return verify_session_token(token)


def _require_user(request: Request):
    user = _get_user(request)
    if not user:
        return None, JSONResponse({"ok": False, "message": "No autenticado."}, status_code=401)
    return user, None


# ── System status ─────────────────────────────────────────────────────────────

@router.get("/status")
async def api_status():
    from pathlib import Path
    import sys
    if getattr(sys, "frozen", False):
        _base = Path(sys._MEIPASS)
    else:
        _base = Path(__file__).resolve().parents[2]
    demo_found = (_base / "Cyber" / "demo_attack_ft.py").exists()
    return {
        "service": "online",
        "mode": "web",
        "broker": settings.broker,
        "broker_port": settings.broker_port,
        "plc_endpoint": settings.plc_endpoint,
        "demo_script_found": demo_found,
    }


# ── Network ───────────────────────────────────────────────────────────────────

@router.get("/network")
async def api_network(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    return get_network_status()


# ── Commands ──────────────────────────────────────────────────────────────────

@router.get("/commands")
async def api_commands(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    return {"ok": True, "commands": get_all_commands()}


@router.get("/commands/by-category")
async def api_commands_by_category(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    return {"ok": True, "categories": get_commands_by_category()}


@router.post("/commands/{command_id}/execute")
async def api_execute(command_id: str, request: Request):
    user, err = _require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}
    params = body.get("params", {}) if isinstance(body, dict) else {}

    from backend.services.command_registry import get_command
    cmd = get_command(command_id)
    if not cmd:
        return JSONResponse({"ok": False, "message": f"Comando desconocido: {command_id}"}, status_code=404)

    exec_id = history_service.start_execution(
        username=user,
        command_id=command_id,
        label=cmd.label,
        category=cmd.category,
    )

    # Run in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, execute, command_id, params, user, exec_id
    )
    return {"ok": result.get("ok", True), "exec_id": exec_id, **result}


@router.post("/commands/{exec_id}/cancel")
async def api_cancel(exec_id: int, request: Request):
    user, err = _require_user(request)
    if err:
        return err
    cancelled = cancel(exec_id)
    if cancelled:
        history_service.finish_execution(exec_id, "cancelled")
    return {"ok": True, "cancelled": cancelled}


@router.get("/operations/active")
async def api_active_operations(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    return {"ok": True, "operations": get_active_operations()}


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history")
async def api_history(request: Request, limit: int = 50, offset: int = 0):
    user, err = _require_user(request)
    if err:
        return err
    rows = history_service.get_history(limit=limit, offset=offset)
    return {"ok": True, "history": rows}


@router.get("/history/stats")
async def api_history_stats(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    return {"ok": True, "stats": history_service.get_stats()}


@router.delete("/history")
async def api_history_clear(request: Request):
    user, err = _require_user(request)
    if err:
        return err
    import sqlite3
    from backend.services.history_service import DB_PATH, _lock
    with _lock:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM executions")
            conn.commit()
    return {"ok": True, "message": "Historial eliminado."}


@router.get("/history/{exec_id}")
async def api_execution_detail(exec_id: int, request: Request):
    user, err = _require_user(request)
    if err:
        return err
    row = history_service.get_execution(exec_id)
    if not row:
        return JSONResponse({"ok": False, "message": "No encontrado."}, status_code=404)
    return {"ok": True, "execution": row}


# ── SSE log stream ────────────────────────────────────────────────────────────

@router.get("/logs/stream")
async def api_logs_stream(request: Request):
    user, err = _require_user(request)
    if err:
        return err

    log_q = get_log_queue()

    async def event_generator() -> AsyncGenerator[str, None]:
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                entry = log_q.get_nowait()
                data = json.dumps(entry)
                yield f"data: {data}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/logs/recent")
async def api_logs_recent(request: Request):
    """Return up to 200 recent log entries from the in-memory queue (non-streaming)."""
    user, err = _require_user(request)
    if err:
        return err
    log_q = get_log_queue()
    entries = []
    while True:
        try:
            entries.append(log_q.get_nowait())
        except queue.Empty:
            break
    return {"ok": True, "logs": entries[-200:]}
