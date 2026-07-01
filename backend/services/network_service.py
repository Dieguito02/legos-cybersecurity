from __future__ import annotations

"""
network_service.py
==================
Detecta el SSID Wi-Fi activo en el sistema operativo y lo compara
con el valor configurado en WIFI_SSID (.env).

Plataformas soportadas:
  - Linux  (nmcli / iwgetid / /proc/net/wireless)
  - macOS  (airport)
  - Windows (netsh)
"""

import re
import subprocess
import sys
from typing import Optional

from backend.core.config import settings

# En Windows con console=False cada subprocess abre su propia ventana de terminal.
# CREATE_NO_WINDOW suprime esa ventana.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0


def get_current_ssid() -> Optional[str]:
    """Devuelve el SSID activo o None si no se puede determinar."""
    try:
        if sys.platform.startswith("linux"):
            return _linux_ssid()
        elif sys.platform == "darwin":
            return _macos_ssid()
        elif sys.platform.startswith("win"):
            return _windows_ssid()
    except Exception:
        pass
    return None


def _linux_ssid() -> Optional[str]:
    # 1. nmcli (NetworkManager)
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            stderr=subprocess.DEVNULL, timeout=4, creationflags=_NO_WINDOW
        ).decode(errors="replace")
        for line in out.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass

    # 2. iwgetid
    try:
        out = subprocess.check_output(
            ["iwgetid", "-r"], stderr=subprocess.DEVNULL, timeout=4, creationflags=_NO_WINDOW
        ).decode(errors="replace").strip()
        if out:
            return out
    except Exception:
        pass

    # 3. ip / iw (iw dev wlan0 info)
    try:
        out = subprocess.check_output(
            ["iw", "dev"], stderr=subprocess.DEVNULL, timeout=4, creationflags=_NO_WINDOW
        ).decode(errors="replace")
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("ssid "):
                return line.split(" ", 1)[1].strip()
    except Exception:
        pass

    return None


def _macos_ssid() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/"
             "Versions/Current/Resources/airport", "-I"],
            stderr=subprocess.DEVNULL, timeout=4, creationflags=_NO_WINDOW
        ).decode(errors="replace")
        for line in out.splitlines():
            m = re.search(r"SSID:\s+(.+)", line)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return None


def _windows_ssid() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            stderr=subprocess.DEVNULL, timeout=4, creationflags=_NO_WINDOW
        ).decode(errors="replace")
        for line in out.splitlines():
            m = re.search(r"SSID\s*:\s+(.+)", line)
            if m and "BSSID" not in line:
                return m.group(1).strip()
    except Exception:
        pass
    return None


def get_network_status() -> dict:
    """
    Devuelve un dict con:
      status:   "ok" | "wrong_network" | "no_connection" | "unconfigured"
      current:  SSID actual (o None)
      expected: SSID esperado (desde .env)
      message:  descripción amigable
    """
    expected = settings.wifi_ssid.strip()

    if not expected:
        return {
            "status": "unconfigured",
            "current": None,
            "expected": None,
            "message": "No se ha configurado WIFI_SSID en .env.",
            "blocked": False,
        }

    current = get_current_ssid()

    if current is None:
        return {
            "status": "no_connection",
            "current": None,
            "expected": expected,
            "message": "Sin conexión inalámbrica detectada.",
            "blocked": True,
        }

    if current == expected:
        return {
            "status": "ok",
            "current": current,
            "expected": expected,
            "message": f"Conectado a la red correcta: {current}",
            "blocked": False,
        }

    return {
        "status": "wrong_network",
        "current": current,
        "expected": expected,
        "message": (
            f"Red incorrecta. Actual: '{current}'. "
            f"Esperada: '{expected}'."
        ),
        "blocked": True,
    }
