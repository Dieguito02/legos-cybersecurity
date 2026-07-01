# build/legos.spec
# ─────────────────────────────────────────────────────────────────────
# Uso desde WSL (Windows Python genera el .exe):
#
#   cd /home/dieguito/demos/legos-front
#   /mnt/c/Users/Dieguito/AppData/Local/Programs/Python/Python311/python.exe \
#       -m PyInstaller build/legos.spec --noconfirm
#
# Resultado: dist/MiAplicacion.exe
# ─────────────────────────────────────────────────────────────────────

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ICON_PATH = str(ROOT / "build" / "icon.ico")

datas = [
    (str(ROOT / "frontend" / "templates"),      "frontend/templates"),
    (str(ROOT / "frontend" / "static"),         "frontend/static"),
    (str(ROOT / "Cyber" / "image"),             "Cyber/image"),
    (str(ROOT / "Cyber" / "demo_attack_ft.py"), "Cyber"),
    (str(ROOT / ".env"),                        "."),
]

hiddenimports = [
    # FastAPI / Starlette
    "fastapi", "fastapi.middleware",
    "starlette", "starlette.routing",
    "starlette.staticfiles", "starlette.templating", "starlette.responses",
    # Uvicorn
    "uvicorn", "uvicorn.main", "uvicorn.config",
    "uvicorn.lifespan.on", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.logging",
    # HTTP
    "h11", "httptools",
    # Templates
    "jinja2", "jinja2.ext",
    # Async
    "anyio", "anyio._backends._asyncio", "sniffio",
    # Env / forms
    "dotenv", "python_dotenv", "multipart", "python_multipart",
    # MQTT
    "paho", "paho.mqtt", "paho.mqtt.client",
    # OpenCV + numpy (camera hijack)
    "cv2",
    "numpy", "numpy.core", "numpy.core._multiarray_umath",
    "numpy.lib", "numpy.lib.stride_tricks",
    # Std
    "email.mime.text", "logging.handlers", "queue", "sqlite3",
]

# numpy NO debe estar en excludes — es requerido por cv2
excludes = [
    "tkinter", "matplotlib",
    "pandas", "scipy", "PyQt5", "PyQt6",
]

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT), str(ROOT / "Cyber")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MiAplicacion",
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=ICON_PATH,
)
