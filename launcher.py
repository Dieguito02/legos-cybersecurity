"""
launcher.py
===========
Arranca FastAPI/uvicorn en un hilo background, espera a que el servidor
responda y abre el navegador predeterminado.

Funciona tanto en modo desarrollo como empaquetado con PyInstaller
(--onefile, console=False).
"""
from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────

def _msgbox(title: str, msg: str) -> None:
    """Muestra un MessageBox de Windows cuando no hay consola disponible."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _find_free_port(start: int = 8000, end: int = 9000) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{end}")


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# ── Resolver BASE_DIR ──────────────────────────────────────────────────

def _setup_paths() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent

    for p in [str(base), str(base / "Cyber")]:
        if p not in sys.path:
            sys.path.insert(0, p)
    return base


# ── Servidor uvicorn en hilo ───────────────────────────────────────────

_server_error: list[str] = []


def _run_server(host: str, port: int) -> None:
    try:
        import uvicorn
        from backend.app import app
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
            log_config=None,   # evita el error "Unable to configure formatter 'default'"
                               # en entornos congelados con PyInstaller
        )
    except Exception as exc:
        _server_error.append(str(exc))


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    base = _setup_paths()

    # Cargar .env — primero buscar junto al .exe, luego en base
    from dotenv import load_dotenv
    if getattr(sys, "frozen", False):
        env_next_to_exe = Path(sys.executable).parent / ".env"
        if env_next_to_exe.exists():
            load_dotenv(dotenv_path=env_next_to_exe, override=True)
        else:
            load_dotenv(dotenv_path=base / ".env", override=False)
    else:
        load_dotenv(dotenv_path=base / ".env", override=False)

    host = os.getenv("HOST", "127.0.0.1")
    requested_port = int(os.getenv("PORT", "0"))
    port = requested_port if requested_port else _find_free_port()
    url  = f"http://{host}:{port}"

    # Arrancar uvicorn en hilo daemon
    t = threading.Thread(target=_run_server, args=(host, port), daemon=True, name="uvicorn")
    t.start()

    # Esperar servidor
    if not _wait_for_server(host, port, timeout=30.0):
        err = _server_error[0] if _server_error else "El servidor no respondió."
        _msgbox("NTT DATA · Error de inicio", f"No se pudo iniciar el servidor:\n\n{err}")
        sys.exit(1)

    # Abrir navegador
    webbrowser.open(url)

    # Mantener proceso vivo
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    # DEBE ser lo primero dentro de __main__ para PyInstaller + multiprocessing
    multiprocessing.freeze_support()
    main()
