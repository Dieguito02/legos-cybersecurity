#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# build/build_exe_from_wsl.sh
#
# Genera MiAplicacion.exe directamente desde WSL.
# NO requiere abrir Windows ni CMD.
#
# Cómo funciona:
#   1. Instala Python 3.11 en Windows vía winget.exe (si no está)
#   2. Instala pyinstaller, pillow y dependencias en Windows Python
#   3. Copia el proyecto a una ruta Windows accesible
#   4. Genera el icono .ico
#   5. Ejecuta pyinstaller con Windows Python → produce el .exe
#   6. Copia el .exe de vuelta al proyecto WSL
#
# Uso (desde la raíz del proyecto en WSL):
#   chmod +x build/build_exe_from_wsl.sh
#   ./build/build_exe_from_wsl.sh
# ═══════════════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Colores ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${CYAN}══ $* ══${NC}"; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  NTT DATA · OT Red Team · Build .EXE desde WSL      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Verificar winget ──────────────────────────────────────────────────
step "1/6  Verificando herramientas"
if ! command -v winget.exe &>/dev/null; then
    error "winget.exe no encontrado. Asegúrate de tener WSL 2 con Windows 10/11."
fi
ok "winget.exe disponible: $(winget.exe --version 2>/dev/null | tr -d '\r')"

# ── Detectar o instalar Python en Windows ─────────────────────────────
step "2/6  Python en Windows"

# Rutas comunes de Python en Windows (accesibles desde WSL vía /mnt)
WIN_PY=""
for candidate in \
    "/mnt/c/Python312/python.exe" \
    "/mnt/c/Python311/python.exe" \
    "/mnt/c/Python310/python.exe" \
    "/mnt/c/Program Files/Python312/python.exe" \
    "/mnt/c/Program Files/Python311/python.exe" \
    "/mnt/c/Program Files/Python310/python.exe" \
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python312/python.exe" \
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python311/python.exe" \
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python310/python.exe"
do
    if [ -x "$candidate" ]; then
        # Verificar que no es el stub de la Store
        if "$candidate" --version &>/dev/null 2>&1; then
            WIN_PY="$candidate"
            break
        fi
    fi
done

# Buscar con winget si no se encontró
if [ -z "$WIN_PY" ]; then
    warn "Python Windows no encontrado. Instalando Python 3.11 vía winget..."
    winget.exe install Python.Python.3.11 \
        --accept-package-agreements \
        --accept-source-agreements \
        --silent 2>/dev/null || true

    # Esperar a que se complete la instalación
    sleep 5

    # Volver a buscar
    for candidate in \
        "/mnt/c/Python311/python.exe" \
        "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python311/python.exe" \
        "/mnt/c/Program Files/Python311/python.exe"
    do
        if [ -x "$candidate" ] && "$candidate" --version &>/dev/null 2>&1; then
            WIN_PY="$candidate"
            break
        fi
    done
fi

# Buscar también en Program Files
if [ -z "$WIN_PY" ]; then
    for candidate in \
        "/mnt/c/Program Files/Python312/python.exe" \
        "/mnt/c/Program Files/Python311/python.exe" \
        "/mnt/c/Program Files/Python310/python.exe" \
        "/mnt/c/Program Files (x86)/Python311/python.exe"
    do
        if [ -x "$candidate" ] && "$candidate" --version &>/dev/null 2>&1; then
            WIN_PY="$candidate"
            break
        fi
    done
fi

# Intentar py launcher de Windows
if [ -z "$WIN_PY" ]; then
    PY_LAUNCHER=$(cmd.exe /c "where py" 2>/dev/null | tr -d '\r' | head -1)
    if [ -n "$PY_LAUNCHER" ]; then
        PY_WSL=$(wslpath "$PY_LAUNCHER" 2>/dev/null)
        if [ -x "$PY_WSL" ] && "$PY_WSL" --version &>/dev/null 2>&1; then
            WIN_PY="$PY_WSL"
        fi
    fi
fi

# Último recurso: buscar cualquier python.exe real en /mnt/c
if [ -z "$WIN_PY" ]; then
    info "Buscando python.exe en disco C (puede tardar unos segundos)..."
    WIN_PY=$(find /mnt/c/Python* \
        "/mnt/c/Program Files/Python311" \
        "/mnt/c/Program Files/Python312" \
        /mnt/c/Users/*/AppData/Local/Programs/Python \
        -name "python.exe" -maxdepth 3 2>/dev/null \
        | while read -r p; do
            "$p" --version &>/dev/null 2>&1 && echo "$p" && break
          done | head -1)
fi

if [ -z "$WIN_PY" ]; then
    echo ""
    echo -e "${RED}No se encontró Python instalado en Windows.${NC}"
    echo ""
    echo "  Instálalo manualmente:"
    echo "    1. Desde PowerShell/CMD en Windows:"
    echo "       winget install Python.Python.3.11"
    echo "    2. O descarga desde: https://www.python.org/downloads/"
    echo "       IMPORTANTE: marca 'Add Python to PATH' al instalar."
    echo "    3. Luego vuelve a ejecutar este script."
    exit 1
fi

WIN_PY_VERSION=$("$WIN_PY" --version 2>&1 | tr -d '\r')
ok "Windows Python: $WIN_PY_VERSION"
ok "Ruta: $WIN_PY"

# Convertir ruta WSL a ruta Windows para usar con pyinstaller
WIN_PY_WIN=$(wslpath -w "$WIN_PY")
WIN_PIP="$(dirname "$WIN_PY")/pip.exe"
WIN_PIP_WIN=$(wslpath -w "$WIN_PIP" 2>/dev/null || echo "")

# ── Instalar dependencias en Windows Python ───────────────────────────
step "3/6  Instalando dependencias en Windows Python"

# Bootstrap pip si no está disponible
if ! "$WIN_PY" -m pip --version &>/dev/null 2>&1; then
    info "Bootstrap pip..."
    "$WIN_PY" -m ensurepip --upgrade 2>/dev/null || \
        curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && \
        "$WIN_PY" /tmp/get-pip.py --quiet
fi

"$WIN_PY" -m pip install --upgrade pip --quiet 2>/dev/null || true
"$WIN_PY" -m pip install pyinstaller pillow --quiet
"$WIN_PY" -m pip install \
    "fastapi" "uvicorn[standard]" "python-dotenv" "jinja2" \
    "python-multipart" "itsdangerous" "paho-mqtt" \
    --quiet

# OpenCV es opcional (camera hijack)
"$WIN_PY" -m pip install opencv-python-headless --quiet 2>/dev/null || \
    warn "opencv-python-headless no instalado (camera hijack no disponible)"

ok "Dependencias instaladas en Windows Python"

# ── Copiar proyecto a ruta Windows ────────────────────────────────────
step "4/6  Preparando directorio de build en Windows"

# Usar un directorio temporal en el disco C de Windows
WIN_TEMP_DIR="/mnt/c/Temp/legos-build"
mkdir -p "$WIN_TEMP_DIR"

# Copiar solo lo necesario (excluir __pycache__, .git, dist, etc.)
info "Copiando proyecto a $WIN_TEMP_DIR..."
rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='dist' \
    --exclude='build/*.exe' \
    --exclude='data/' \
    "$PROJECT_DIR/" "$WIN_TEMP_DIR/"

ok "Proyecto copiado"

# ── Generar icono ──────────────────────────────────────────────────────
step "5/6  Generando icono NTT DATA"

WIN_TEMP_WIN=$(wslpath -w "$WIN_TEMP_DIR")
"$WIN_PY" "$WIN_TEMP_DIR/build/make_icon.py" && ok "icon.ico generado"

# ── Compilar .exe ─────────────────────────────────────────────────────
step "6/6  Compilando MiAplicacion.exe con PyInstaller"
info "Esto puede tardar 3-8 minutos..."

cd "$WIN_TEMP_DIR"
"$WIN_PY" -m PyInstaller build/legos.spec --noconfirm --clean

cd "$PROJECT_DIR"

EXE_PATH="$WIN_TEMP_DIR/dist/MiAplicacion.exe"
if [ ! -f "$EXE_PATH" ]; then
    error "No se generó $EXE_PATH. Revisa los mensajes anteriores."
fi

# ── Copiar .exe de vuelta al proyecto ─────────────────────────────────
mkdir -p "$PROJECT_DIR/dist"
cp "$EXE_PATH" "$PROJECT_DIR/dist/MiAplicacion.exe"
ok "EXE copiado a: $PROJECT_DIR/dist/MiAplicacion.exe"

# Copiar también el icono al proyecto original
cp "$WIN_TEMP_DIR/build/icon.ico" "$PROJECT_DIR/build/icon.ico" 2>/dev/null || true

# ── Resultado ─────────────────────────────────────────────────────────
EXE_SIZE_MB=$(du -m "$PROJECT_DIR/dist/MiAplicacion.exe" | cut -f1)

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   BUILD EXITOSO                                      ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}   Archivo: dist/MiAplicacion.exe                     ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   Tamaño:  ${EXE_SIZE_MB} MB                                       ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Para ejecutar desde Windows:"
echo "    dist\\MiAplicacion.exe"
echo ""
echo "  Para distribuir, incluye junto al .exe:"
echo "    .env  (con credenciales de producción)"
echo ""

# Limpiar directorio temporal
info "Limpiando directorio temporal..."
rm -rf "$WIN_TEMP_DIR" 2>/dev/null || true
