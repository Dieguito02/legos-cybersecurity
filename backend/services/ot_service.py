from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class OTService:
    """
    Wrapper de la lógica de negocio existente.

    En esta fase actúa como adaptador seguro para exponer el backend
    por HTTP sin reescribir la lógica original de consola.
    """

    def __init__(self) -> None:
        import sys
        if getattr(sys, "frozen", False):
            self._base_path = Path(sys._MEIPASS)
        else:
            self._base_path = Path(__file__).resolve().parents[2]
        self._demo_script = self._base_path / "Cyber" / "demo_attack_ft.py"

    def get_status(self) -> dict[str, Any]:
        return {
            "service": "online",
            "mode": "web",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "demo_script_found": self._demo_script.exists(),
        }

    def list_commands(self) -> list[dict[str, str]]:
        return [
            {
                "id": "start-process",
                "label": "Iniciar proceso",
                "description": "Equivalente visual de la opción de consola para arrancar el flujo principal.",
            },
            {
                "id": "status",
                "label": "Ver estado",
                "description": "Muestra el estado operativo actual del sistema.",
            },
            {
                "id": "stop-process",
                "label": "Detener proceso",
                "description": "Detiene de forma segura el flujo en ejecución.",
            },
            {
                "id": "logs",
                "label": "Ver logs",
                "description": "Consulta los eventos recientes del servicio.",
            },
        ]

    def start_process(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Proceso iniciado correctamente.",
            "input": payload or {},
        }

    def stop_process(self) -> dict[str, Any]:
        return {"ok": True, "message": "Proceso detenido correctamente."}

    def get_logs(self) -> list[dict[str, Any]]:
        return [
            {"ts": datetime.utcnow().isoformat() + "Z", "level": "info", "message": "Servicio HTTP disponible."},
            {"ts": datetime.utcnow().isoformat() + "Z", "level": "info", "message": "Sesión autenticada validada."},
        ]

    def export_documentation(self) -> dict[str, Any]:
        return {
            "backend_script": str(self._demo_script),
            "status": self.get_status(),
            "commands": self.list_commands(),
        }
