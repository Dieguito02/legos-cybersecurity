from __future__ import annotations

"""
command_registry.py
===================
Registro centralizado de todos los comandos del toolkit.

Cada comando tiene:
  - id          : identificador único (slug)
  - label       : nombre visible en UI
  - category    : agrupación (MQTT L1, MQTT L3, OPC-UA, CONTROL…)
  - description : qué hace la operación
  - key         : tecla original de consola (solo referencia interna)
  - background  : si genera un proceso background que puede cancelarse
  - params      : lista de parámetros opcionales que puede recibir

La ejecución real se delega a CommandExecutor (command_executor.py).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommandParam:
    name: str
    label: str
    type: str = "text"         # text | number | select
    required: bool = False
    default: Any = None
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    category: str
    description: str
    key: str = ""
    background: bool = False
    cancellable: bool = False
    params: list[CommandParam] = field(default_factory=list)
    danger_level: str = "low"  # low | medium | high | critical


REGISTRY: list[Command] = [
    # ── MQTT · L1 ─────────────────────────────────────────────────────
    Command(
        id="mqtt_order_red",
        label="Order RED",
        category="MQTT · L1",
        description="Publica una orden de producción RED al bus MQTT. "
                    "Inicia ciclo completo HBW→VGR→MPO→SLD→DPS (~2-3 min).",
        key="1",
        danger_level="medium",
    ),
    Command(
        id="mqtt_order_blue",
        label="Order BLUE",
        category="MQTT · L1",
        description="Publica una orden de producción BLUE al bus MQTT.",
        key="2",
        danger_level="medium",
    ),
    Command(
        id="mqtt_order_white",
        label="Order WHITE",
        category="MQTT · L1",
        description="Publica una orden de producción WHITE al bus MQTT.",
        key="3",
        danger_level="medium",
    ),
    Command(
        id="mqtt_ptu_dance",
        label="PTU Dance",
        category="MQTT · L1",
        description="Camera misdirection. Barrido lateral → cámara al techo 10s "
                    "(ventana ciega) → retorno al centro.",
        key="4",
        danger_level="medium",
    ),

    # ── MQTT · L3 ─────────────────────────────────────────────────────
    Command(
        id="mqtt_sensor_spoof",
        label="Sensor Spoof",
        category="MQTT · L3",
        description="Inyecta lecturas nominales falsas (22.5°C) en el topic "
                    "i/bme680 a 800ms, enterrando el sensor real.",
        key="7",
        background=True,
        cancellable=True,
        danger_level="high",
    ),
    Command(
        id="mqtt_sensor_alarm",
        label="Sensor Alarm",
        category="MQTT · L3",
        description="Inyecta 87°C crítico sostenido en i/bme680. "
                    "Dispara protocolo de evacuación en el HMI.",
        key="9",
        background=True,
        cancellable=True,
        danger_level="critical",
    ),

    # ── MQTT · L4 ─────────────────────────────────────────────────────
    Command(
        id="mqtt_chaos_busy",
        label="Chaos Busy",
        category="MQTT · L4",
        description="Marca simultáneamente todas las estaciones (HBW/VGR/MPO/SLD) "
                    "como BUSY en loop. La fábrica parece ocupada, cero movimiento real.",
        key="c",
        background=True,
        cancellable=True,
        danger_level="critical",
    ),
    Command(
        id="mqtt_ghost_stock",
        label="Ghost Stock",
        category="MQTT · L4",
        description="Publica 9 piezas fantasma en f/i/stock. "
                    "ERP y dashboard MQTT ven rack lleno. Stock real ignorado.",
        key="g",
        background=True,
        cancellable=True,
        danger_level="high",
    ),
    Command(
        id="mqtt_reset_state",
        label="Reset State",
        category="MQTT · L4",
        description="Detiene todos los ataques background y envía estado IDLE "
                    "a todas las estaciones. HUD limpio durante <1s.",
        key="R",
        danger_level="low",
    ),

    # ── MQTT · L5 ─────────────────────────────────────────────────────
    Command(
        id="mqtt_fire_loop",
        label="Fire Loop",
        category="MQTT · L5",
        description="Publica frames de incendio base64 en i/cam a 1Hz. "
                    "El operador ve fuego en la cámara → evacuación.",
        key="v",
        background=True,
        cancellable=True,
        danger_level="critical",
    ),
    Command(
        id="mqtt_freeze_frame",
        label="Freeze Frame",
        category="MQTT · L5",
        description="Captura un frame real y lo republica en loop. "
                    "La cámara parece funcionar pero está congelada (invisible blindfold).",
        key="V",
        background=True,
        cancellable=True,
        danger_level="critical",
    ),

    # ── MQTT · L6 ─────────────────────────────────────────────────────
    Command(
        id="mqtt_eavesdrop",
        label="Eavesdrop",
        category="MQTT · L6",
        description="Suscripción pasiva al wildcard # durante 12s. "
                    "Mapea topics, NFC IDs, órdenes y sensores sin publicar nada.",
        key="E",
        params=[
            CommandParam("seconds", "Duración (s)", "number", default=12),
        ],
        danger_level="low",
    ),
    Command(
        id="mqtt_takeover",
        label="Takeover",
        category="MQTT · L6",
        description="Ransomware-style: 5 ataques encadenados en <20s. "
                    "Chaos busy + sensor alarm + ghost stock + fake shipped + fire loop.",
        key="T",
        background=True,
        cancellable=True,
        danger_level="critical",
    ),

    # ── OPC-UA ────────────────────────────────────────────────────────
    Command(
        id="opcua_discover",
        label="Discover",
        category="OPC-UA",
        description="Recorre el árbol de nodos del S7-1500 sin autenticación "
                    "(modo anónimo, sin TLS). Hasta 6 niveles de profundidad.",
        key="d",
        params=[
            CommandParam("max_depth", "Profundidad máx.", "number", default=6),
        ],
        danger_level="low",
    ),
    Command(
        id="opcua_browse",
        label="Browse",
        category="OPC-UA",
        description="Enumera namespace y lee variables clave conocidas del PLC "
                    "(setup buttons, SSC thresholds, error flags, FW version).",
        key="b",
        danger_level="low",
    ),
    Command(
        id="opcua_read",
        label="Read Plant Snapshot",
        category="OPC-UA",
        description="Snapshot completo del estado interno del PLC: "
                    "todas las variables de TARGETS_READ.",
        key="n",
        danger_level="low",
    ),
    Command(
        id="opcua_inspect",
        label="Inspect Variable",
        category="OPC-UA",
        description="Examina el esquema y tipo de una variable OPC-UA específica "
                    "(browse name, data type, array dims, access level, valor actual).",
        key="i",
        params=[
            CommandParam(
                "target",
                "Variable (ej: gtyp_HBW.Rack_Workpiece)",
                "text",
                required=True,
                default="gtyp_HBW.Rack_Workpiece",
            ),
        ],
        danger_level="low",
    ),
    Command(
        id="opcua_ghost_real",
        label="Ghost Real",
        category="OPC-UA",
        description="Sobreescribe Rack_Workpiece en el PLC con 9 piezas fantasma. "
                    "Afecta al HMI oficial y al scheduler del controlador.",
        key="G",
        danger_level="critical",
    ),
    Command(
        id="opcua_save_snapshot",
        label="Save Snapshot",
        category="OPC-UA",
        description="Guarda el inventario real del rack HBW a un archivo JSON "
                    "antes del ataque (para poder restaurar).",
        key="s",
        danger_level="low",
    ),
    Command(
        id="opcua_restore_snapshot",
        label="Restore Snapshot",
        category="OPC-UA",
        description="Restaura el inventario del rack HBW desde el snapshot guardado. "
                    "Reescribe el PLC con los valores originales.",
        key="Z",
        danger_level="high",
    ),
    Command(
        id="opcua_trigger_park",
        label="Trigger Park",
        category="OPC-UA",
        description="Escribe True en gtyp_Setup.x_Park_Position. "
                    "Mueve físicamente todas las estaciones a posición de parking.",
        key="P",
        danger_level="high",
    ),
    Command(
        id="opcua_monitor",
        label="Monitor Variables",
        category="OPC-UA",
        description="Suscripción OPC-UA en tiempo real a ~40 variables del PLC. "
                    "Muestra cada cambio con timestamp.",
        key="M",
        background=True,
        cancellable=True,
        params=[
            CommandParam("duration", "Duración (s)", "number", default=60),
        ],
        danger_level="low",
    ),

    # ── CONTROL ───────────────────────────────────────────────────────
    Command(
        id="ctrl_stop_all",
        label="Stop All Background Operations",
        category="CONTROL",
        description="Detiene todos los ataques en background: "
                    "camera hijack, sensor spoof, state injections.",
        key="X",
        danger_level="low",
    ),
]

# Fast lookup by id
_BY_ID: dict[str, Command] = {cmd.id: cmd for cmd in REGISTRY}


def get_command(cmd_id: str) -> Command | None:
    return _BY_ID.get(cmd_id)


def get_all_commands() -> list[dict]:
    return [_cmd_to_dict(c) for c in REGISTRY]


def get_commands_by_category() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for cmd in REGISTRY:
        result.setdefault(cmd.category, []).append(_cmd_to_dict(cmd))
    return result


def _cmd_to_dict(cmd: Command) -> dict:
    return {
        "id": cmd.id,
        "label": cmd.label,
        "category": cmd.category,
        "description": cmd.description,
        "key": cmd.key,
        "background": cmd.background,
        "cancellable": cmd.cancellable,
        "danger_level": cmd.danger_level,
        "params": [
            {
                "name": p.name,
                "label": p.label,
                "type": p.type,
                "required": p.required,
                "default": p.default,
                "options": p.options,
            }
            for p in cmd.params
        ],
    }
