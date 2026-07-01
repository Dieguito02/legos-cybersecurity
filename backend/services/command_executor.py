from __future__ import annotations

"""
command_executor.py
===================
Ejecuta los comandos reales del toolkit usando la lógica de ShowroomDemo.

- Los comandos background se arrancan en threads daemon.
- Un dict global _RUNNING guarda los threads/eventos activos (para cancelar).
- Los logs se envían a una cola asyncio que SSE lee en tiempo real.
"""

import asyncio
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Añadir Cyber/ al path para importar demo_attack_ft sin modificarlo
if getattr(sys, "frozen", False):
    _CYBER_DIR = Path(sys._MEIPASS) / "Cyber"
else:
    _CYBER_DIR = Path(__file__).resolve().parents[2] / "Cyber"
if str(_CYBER_DIR) not in sys.path:
    sys.path.insert(0, str(_CYBER_DIR))

from backend.core.config import settings
from backend.services import history_service

# ── Shared log queue (SSE consumers read from here) ──────────────────
_log_queue: queue.Queue = queue.Queue(maxsize=2000)
# ── Active background tasks: exec_id → {"thread", "stop_event"} ─────
_RUNNING: dict[int, dict] = {}
_RUNNING_LOCK = threading.Lock()


def push_log(level: str, message: str, exec_id: int | None = None) -> None:
    """Push a log entry to the SSE queue."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "exec_id": exec_id,
    }
    try:
        _log_queue.put_nowait(entry)
    except queue.Full:
        pass  # drop oldest is not ideal, but prevents blocking


def get_log_queue() -> queue.Queue:
    return _log_queue


# ── Demo instance (lazy, single) ─────────────────────────────────────
_demo_instance: Any = None
_demo_lock = threading.Lock()


def _get_demo():
    global _demo_instance
    with _demo_lock:
        if _demo_instance is None:
            try:
                # Cuando console=False (PyInstaller) en Windows:
                #   - sys.stdout/stderr/stdin son None → crash en isatty()
                #   - os.get_terminal_size() lanza ValueError (no OSError)
                #     porque los fd 0/1/2 a nivel OS son inválidos.
                # demo_attack_ft tiene `except OSError` pero NO `except ValueError`.
                import os as _os

                if sys.stdout is None:
                    sys.stdout = open(_os.devnull, "w", encoding="utf-8", errors="replace")
                if sys.stderr is None:
                    sys.stderr = open(_os.devnull, "w", encoding="utf-8", errors="replace")
                if sys.stdin is None:
                    sys.stdin = open(_os.devnull, "r", encoding="utf-8")

                # Parchear os.get_terminal_size para capturar ValueError además de OSError
                _orig_terminal_size = _os.get_terminal_size
                def _safe_terminal_size(*args, **kwargs):
                    try:
                        return _orig_terminal_size(*args, **kwargs)
                    except (OSError, ValueError):
                        return _os.terminal_size((76, 24))
                _os.get_terminal_size = _safe_terminal_size

                import demo_attack_ft as ft  # type: ignore[import]
                # Patch broker/port from .env
                ft.BROKER = settings.broker
                ft.PORT = settings.broker_port
                ft.ENDPOINT = settings.plc_endpoint
                _demo_instance = ft.ShowroomDemo()
                push_log("info", f"MQTT conectado a {settings.broker}:{settings.broker_port}")
            except Exception as exc:
                push_log("error", f"No se pudo conectar al broker MQTT: {exc}")
                raise
    return _demo_instance


def _try_get_demo():
    """Return demo or None (never raises)."""
    try:
        return _get_demo()
    except Exception:
        return None


# ── Executor ─────────────────────────────────────────────────────────

def execute(
    command_id: str,
    params: dict,
    username: str,
    exec_id: int,
) -> dict:
    """
    Dispatch the command. Returns immediately for background commands;
    blocks until complete for foreground ones.
    """
    handlers = {
        # MQTT L1
        "mqtt_order_red":      _mqtt_order_red,
        "mqtt_order_blue":     _mqtt_order_blue,
        "mqtt_order_white":    _mqtt_order_white,
        "mqtt_ptu_dance":      _mqtt_ptu_dance,
        # MQTT L3
        "mqtt_sensor_spoof":   _mqtt_sensor_spoof,
        "mqtt_sensor_alarm":   _mqtt_sensor_alarm,
        # MQTT L4
        "mqtt_chaos_busy":     _mqtt_chaos_busy,
        "mqtt_ghost_stock":    _mqtt_ghost_stock,
        "mqtt_reset_state":    _mqtt_reset_state,
        # MQTT L5
        "mqtt_fire_loop":      _mqtt_fire_loop,
        "mqtt_freeze_frame":   _mqtt_freeze_frame,
        # MQTT L6
        "mqtt_eavesdrop":      _mqtt_eavesdrop,
        "mqtt_takeover":       _mqtt_takeover,
        # OPC-UA
        "opcua_discover":      _opcua_discover,
        "opcua_browse":        _opcua_browse,
        "opcua_read":          _opcua_read,
        "opcua_inspect":       _opcua_inspect,
        "opcua_ghost_real":    _opcua_ghost_real,
        "opcua_save_snapshot": _opcua_save_snapshot,
        "opcua_restore_snapshot": _opcua_restore_snapshot,
        "opcua_trigger_park":  _opcua_trigger_park,
        "opcua_monitor":       _opcua_monitor,
        # CONTROL
        "ctrl_stop_all":       _ctrl_stop_all,
    }
    fn = handlers.get(command_id)
    if fn is None:
        history_service.finish_execution(exec_id, "error", error=f"Unknown command: {command_id}")
        return {"ok": False, "error": f"Unknown command: {command_id}"}
    try:
        result = fn(params, exec_id)
        return result or {"ok": True}
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def cancel(exec_id: int) -> bool:
    with _RUNNING_LOCK:
        entry = _RUNNING.get(exec_id)
    if not entry:
        return False
    stop_ev = entry.get("stop_event")
    if stop_ev:
        stop_ev.set()
    return True


def _register_bg(exec_id: int, thread: threading.Thread, stop_event: threading.Event):
    with _RUNNING_LOCK:
        _RUNNING[exec_id] = {"thread": thread, "stop_event": stop_event}


def _unregister_bg(exec_id: int):
    with _RUNNING_LOCK:
        _RUNNING.pop(exec_id, None)


# ── MQTT L1 ──────────────────────────────────────────────────────────

def _mqtt_order_red(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden RED → f/o/order", exec_id)
    demo.order("RED")
    push_log("success", "Orden RED publicada. Ciclo iniciado en la fábrica.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "RED"})
    return {"ok": True, "message": "Orden RED enviada al bus MQTT."}


def _mqtt_order_blue(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden BLUE → f/o/order", exec_id)
    demo.order("BLUE")
    push_log("success", "Orden BLUE publicada.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "BLUE"})
    return {"ok": True, "message": "Orden BLUE enviada al bus MQTT."}


def _mqtt_order_white(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden WHITE → f/o/order", exec_id)
    demo.order("WHITE")
    push_log("success", "Orden WHITE publicada.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "WHITE"})
    return {"ok": True, "message": "Orden WHITE enviada al bus MQTT."}


def _mqtt_ptu_dance(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}

    def run():
        try:
            push_log("info", "PTU Dance: iniciando secuencia de misdirection", exec_id)
            demo.ptu_dance()
            push_log("success", "PTU Dance completo.", exec_id)
            history_service.finish_execution(exec_id, "success")
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            _unregister_bg(exec_id)

    stop_ev = threading.Event()
    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev)
    t.start()
    return {"ok": True, "message": "PTU Dance iniciado en background.", "exec_id": exec_id}


# ── MQTT L3 ──────────────────────────────────────────────────────────

def _start_bg_monitor(exec_id: int, label: str, is_running_fn, stop_fn=None) -> None:
    """
    Inicia un hilo monitor para comandos background del demo que no tienen
    su propio hilo explícito. Mantiene el exec_id en _RUNNING mientras
    is_running_fn() retorne True.
    """
    stop_ev = threading.Event()

    def _monitor():
        try:
            while is_running_fn() and not stop_ev.is_set():
                time.sleep(0.5)
        finally:
            _unregister_bg(exec_id)

    t = threading.Thread(target=_monitor, daemon=True, name=f"bg-monitor-{exec_id}")
    _register_bg(exec_id, t, stop_ev)
    t.start()


def _mqtt_sensor_spoof(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.start_fake_sensor()
    push_log("warn", "Sensor spoof iniciado: 22.5°C nominal loop → i/bme680", exec_id)
    history_service.finish_execution(exec_id, "success", result={"mode": "nominal"})
    _start_bg_monitor(exec_id, "sensor_spoof", lambda: demo.fake_sensor_running)
    return {"ok": True, "message": "Sensor spoof activo (22.5°C). Use Stop All para detener."}


def _mqtt_sensor_alarm(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.dramatic_sensor()
    push_log("warn", "Sensor ALARM iniciado: 87.3°C crítico loop → i/bme680", exec_id)
    history_service.finish_execution(exec_id, "success", result={"mode": "alarm", "temp": 87.3})
    _start_bg_monitor(exec_id, "sensor_alarm", lambda: demo.fake_sensor_running)
    return {"ok": True, "message": "Sensor alarm activo (87.3°C). Use Stop All para detener."}


# ── MQTT L4 ──────────────────────────────────────────────────────────

def _mqtt_chaos_busy(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.chaos_busy()
    push_log("warn", "Chaos busy iniciado: HBW/VGR/MPO/SLD BUSY en loop", exec_id)
    history_service.finish_execution(exec_id, "success")
    _start_bg_monitor(exec_id, "chaos_busy", lambda: bool(demo._active_injections()))
    return {"ok": True, "message": "Chaos busy activo. Use Stop All para detener."}


def _mqtt_ghost_stock(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.ghost_stock()
    push_log("warn", "Ghost stock iniciado: 9 piezas fantasma en f/i/stock", exec_id)
    history_service.finish_execution(exec_id, "success", result={"phantom_pieces": 9})
    _start_bg_monitor(exec_id, "ghost_stock", lambda: bool(demo._active_injections()))
    return {"ok": True, "message": "Ghost stock activo. Use Stop All para detener."}


def _mqtt_reset_state(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.reset_state()
    push_log("info", "Reset state: todas las estaciones → IDLE", exec_id)
    history_service.finish_execution(exec_id, "success")
    return {"ok": True, "message": "Estado reseteado. PLC republicará en el próximo latido."}


# ── MQTT L5 ──────────────────────────────────────────────────────────

def _mqtt_fire_loop(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}

    # Diagnóstico previo: cv2 y rutas de imágenes
    import os as _os2
    try:
        import cv2 as _cv2
        push_log("info", f"cv2 {_cv2.__version__} disponible", exec_id)
    except ImportError as e:
        msg = f"opencv no disponible en el .exe: {e}"
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}

    if getattr(sys, "frozen", False):
        _img_dir = Path(sys._MEIPASS) / "Cyber" / "image"
    else:
        _img_dir = _CYBER_DIR / "image"
    push_log("info", f"img_dir: {_img_dir} exists={_img_dir.exists()}", exec_id)
    for _fn in ["fire_1.png", "fire_2.png", "fire_3.png"]:
        _fp = _img_dir / _fn
        push_log("info", f"  {_fn}: exists={_fp.exists()}", exec_id)

    demo.start_cam_fire(announce=False)
    # Verificar que el hijack realmente arrancó (falla silenciosa si cv2 o imágenes faltan)
    if not demo.cam_hijack_running:
        msg = ("Fire loop no iniciado tras start_cam_fire(). "
               "Revisar logs de diagnóstico anteriores.")
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}
    push_log("warn", "Fire loop activo: frames de incendio → i/cam @ 1Hz", exec_id)
    history_service.finish_execution(exec_id, "success", result={"mode": "fire"})
    _start_bg_monitor(exec_id, "fire_loop", lambda: demo.cam_hijack_running)
    return {"ok": True, "message": "Fire loop activo. Use Stop All para detener."}


def _mqtt_freeze_frame(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.start_cam_freeze()
    if not demo.cam_hijack_running:
        msg = ("Freeze frame no iniciado. "
               "Verifica: opencv-python-headless instalado y archivos Cyber/image/*.png presentes.")
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}
    push_log("warn", "Freeze frame activo: frame congelado en loop → i/cam", exec_id)
    history_service.finish_execution(exec_id, "success", result={"mode": "freeze"})
    _start_bg_monitor(exec_id, "freeze_frame", lambda: demo.cam_hijack_running)
    return {"ok": True, "message": "Freeze frame activo. Use Stop All para detener."}


# ── MQTT L6 ──────────────────────────────────────────────────────────

def _mqtt_eavesdrop(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}
    seconds = int(params.get("seconds", 12))
    results = {"topics": {}, "nfc_ids": [], "orders": []}

    def run():
        try:
            push_log("info", f"Eavesdrop: sniffing {seconds}s en wildcard #", exec_id)
            import re
            received = []

            def on_msg(c, u, m):
                try:
                    payload = m.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = "<binary>"
                received.append((m.topic, payload))
                results["topics"][m.topic] = results["topics"].get(m.topic, 0) + 1
                for match in re.finditer(r'"id"\s*:\s*"([^"]+)"', payload):
                    if match.group(1) not in results["nfc_ids"]:
                        results["nfc_ids"].append(match.group(1))
                for match in re.finditer(r'"type"\s*:\s*"(RED|BLUE|WHITE)"', payload):
                    if match.group(1) not in results["orders"]:
                        results["orders"].append(match.group(1))
                push_log("info", f"[{m.topic}] {payload[:80]}", exec_id)

            demo.client.message_callback_add("#", on_msg)
            demo.client.subscribe("#", qos=0)
            time.sleep(seconds)
            demo.client.unsubscribe("#")
            demo.client.message_callback_remove("#")

            summary = (f"Eavesdrop completo: {len(received)} msgs, "
                       f"{len(results['topics'])} topics, "
                       f"NFC: {results['nfc_ids'][:5]}")
            push_log("success", summary, exec_id)
            history_service.finish_execution(exec_id, "success", result=results)
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            _unregister_bg(exec_id)

    stop_ev = threading.Event()
    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev)
    t.start()
    return {"ok": True, "message": f"Eavesdrop iniciado ({seconds}s).", "exec_id": exec_id}


def _mqtt_takeover(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        return {"ok": False, "error": "Broker MQTT no disponible"}

    def run():
        try:
            push_log("warn", "TAKEOVER: iniciando 5 ataques encadenados", exec_id)
            import threading as _th
            steps = [
                ("Chaos busy",     demo.chaos_busy),
                ("Sensor alarm",   demo.dramatic_sensor),
                ("Ghost stock",    demo.ghost_stock),
                ("PTU dance",      demo.ptu_dance),
                ("Fire loop",      lambda: demo.start_cam_fire(announce=False)),
            ]
            threads = [_th.Thread(target=fn, daemon=True) for _, fn in steps]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            push_log("warn", "TAKEOVER completo: planta comprometida al 100%", exec_id)
            history_service.finish_execution(exec_id, "success")
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            _unregister_bg(exec_id)

    stop_ev = threading.Event()
    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev)
    t.start()
    return {"ok": True, "message": "Takeover iniciado en background.", "exec_id": exec_id}


# ── OPC-UA ───────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an asyncio coroutine in a new event loop (from a sync thread)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _opcua_discover(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        max_depth = int(params.get("max_depth", 6))
        push_log("info", f"OPC-UA Discover: depth={max_depth} → {settings.plc_endpoint}", exec_id)
        _run_async(ft.cmd_discover(max_depth))
        push_log("success", "Discover completo.", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Discover completado. Ver logs para resultados."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_browse(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("info", f"OPC-UA Browse → {settings.plc_endpoint}", exec_id)
        _run_async(ft.cmd_browse())
        push_log("success", "Browse completo.", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Browse completado. Ver logs."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_read(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("info", "OPC-UA Read Plant Snapshot", exec_id)
        _run_async(ft.cmd_read())
        push_log("success", "Snapshot leído.", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Snapshot completo. Ver logs."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_inspect(params, exec_id):
    target = params.get("target", "gtyp_HBW.Rack_Workpiece")
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("info", f"OPC-UA Inspect: {target}", exec_id)
        _run_async(ft.cmd_inspect(target))
        push_log("success", f"Inspect de {target} completo.", exec_id)
        history_service.finish_execution(exec_id, "success", result={"target": target})
        return {"ok": True, "message": f"Inspect de '{target}' completado. Ver logs."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_ghost_real(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("warn", "OPC-UA Ghost Real: sobreescribiendo Rack_Workpiece con 9 piezas fantasma", exec_id)
        _run_async(ft.cmd_ghost("real"))
        push_log("warn", "Ghost real completo. HMI oficial afectado.", exec_id)
        history_service.finish_execution(exec_id, "success", result={"phantom_pieces": 9})
        return {"ok": True, "message": "9 piezas fantasma escritas en el PLC."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_save_snapshot(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("info", "OPC-UA Save Snapshot: guardando inventario real", exec_id)
        _run_async(ft.cmd_ghost("snapshot"))
        push_log("success", "Snapshot guardado en inventory_backup.json", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Snapshot guardado."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_restore_snapshot(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("warn", "OPC-UA Restore Snapshot: restaurando inventario original", exec_id)
        _run_async(ft.cmd_ghost("restore"))
        push_log("success", "Inventario restaurado en el PLC.", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Inventario restaurado desde snapshot."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_trigger_park(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        push_log("warn", "OPC-UA Trigger Park: enviando estaciones a parking", exec_id)
        _run_async(ft.cmd_alert("park"))
        push_log("success", "Trigger park completado. Estaciones en movimiento.", exec_id)
        history_service.finish_execution(exec_id, "success")
        return {"ok": True, "message": "Todas las estaciones enviadas a parking."}
    except Exception as e:
        msg = str(e)
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def _opcua_monitor(params, exec_id):
    duration = int(params.get("duration", 60))
    try:
        import demo_attack_ft as ft  # type: ignore[import]
    except Exception as e:
        return {"ok": False, "error": str(e)}

    def run():
        try:
            push_log("info", f"OPC-UA Monitor: suscripción a ~40 variables · {duration}s", exec_id)
            _run_async(ft.cmd_monitor(duration))
            push_log("success", f"Monitor completado ({duration}s).", exec_id)
            history_service.finish_execution(exec_id, "success")
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            _unregister_bg(exec_id)

    stop_ev = threading.Event()
    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev)
    t.start()
    return {"ok": True, "message": f"Monitor OPC-UA iniciado ({duration}s).", "exec_id": exec_id}


# ── CONTROL ──────────────────────────────────────────────────────────

def _ctrl_stop_all(params, exec_id):
    demo = _try_get_demo()
    if demo:
        demo.stop_all_background()
        push_log("info", "Stop All: todos los ataques background detenidos", exec_id)
    else:
        push_log("info", "Stop All: sin demo activo", exec_id)
    history_service.finish_execution(exec_id, "success")
    return {"ok": True, "message": "Todos los procesos background detenidos."}


def get_active_operations() -> list[dict]:
    """Return list of currently running background exec_ids."""
    with _RUNNING_LOCK:
        return [{"exec_id": eid} for eid in _RUNNING.keys()]
