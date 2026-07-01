from __future__ import annotations

"""
heartbeat.py
============
Endpoint de latido para el watchdog de inactividad.

El frontend llama a  POST /api/heartbeat  cada 30 segundos.
Si no recibe ningún latido durante INACTIVITY_TIMEOUT_SECONDS,
el proceso se cierra automáticamente.
"""

import os
import sys
import threading
import time

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["heartbeat"])

# ── Configuración ─────────────────────────────────────────────────────
# Tiempo en segundos sin latido antes de cerrar la aplicación.
# Se puede sobrescribir con la variable de entorno INACTIVITY_TIMEOUT.
_DEFAULT_TIMEOUT = 300  # 5 minutos


def _get_timeout() -> int:
    try:
        return int(os.getenv("INACTIVITY_TIMEOUT", str(_DEFAULT_TIMEOUT)))
    except ValueError:
        return _DEFAULT_TIMEOUT


# ── Estado compartido ─────────────────────────────────────────────────
_last_seen: float = time.monotonic()
_watchdog_started: bool = False
_lock = threading.Lock()


def _reset_timer() -> None:
    global _last_seen
    with _lock:
        _last_seen = time.monotonic()


def _watchdog_loop(timeout: int) -> None:
    """Hilo daemon que comprueba inactividad cada 10 segundos."""
    while True:
        time.sleep(10)
        with _lock:
            idle = time.monotonic() - _last_seen
        if idle >= timeout:
            # os._exit(0) cierra el proceso desde un thread daemon.
            # sys.exit() solo lanza SystemExit en el thread actual y uvicorn lo captura.
            import os as _os
            _os._exit(0)


def start_watchdog() -> None:
    """Arranca el hilo watchdog una sola vez."""
    global _watchdog_started
    if _watchdog_started:
        return
    timeout = _get_timeout()
    if timeout <= 0:
        return  # desactivado
    _watchdog_started = True
    t = threading.Thread(
        target=_watchdog_loop,
        args=(timeout,),
        daemon=True,
        name="inactivity-watchdog",
    )
    t.start()


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/heartbeat")
async def heartbeat():
    """
    El frontend llama a este endpoint periódicamente para indicar
    que el usuario sigue activo. Reinicia el contador de inactividad.
    """
    _reset_timer()
    return {"ok": True, "ts": time.monotonic()}


@router.get("/heartbeat/status")
async def heartbeat_status():
    """Devuelve el tiempo de inactividad actual (útil para debugging)."""
    timeout = _get_timeout()
    with _lock:
        idle = time.monotonic() - _last_seen
    return {
        "ok": True,
        "idle_seconds": round(idle, 1),
        "timeout_seconds": timeout,
        "will_exit_in": max(0, round(timeout - idle, 1)),
    }
