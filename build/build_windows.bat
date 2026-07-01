@echo off
REM ═══════════════════════════════════════════════════════════════════
REM  NTT DATA · OT Red Team Showroom — Build Script para Windows
REM  Genera:  dist\MiAplicacion.exe
REM
REM  REQUISITOS:
REM    - Python 3.11+ instalado en Windows (python.org — no la del Store)
REM    - El proyecto copiado en una ruta Windows (ej: C:\Projects\legos-front)
REM
REM  USO (desde CMD o PowerShell en la raíz del proyecto):
REM    build\build_windows.bat
REM ═══════════════════════════════════════════════════════════════════

setlocal EnableDelayedExpansion

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║   NTT DATA · OT Red Team · Build Windows EXE            ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Verificar Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado.
    echo          Descarga Python 3.11+ desde https://www.python.org
    echo          Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo  [OK] %PYVER%

REM ── Verificar directorio del proyecto ────────────────────────────
if not exist "launcher.py" (
    echo  [ERROR] Ejecuta este script desde la raiz del proyecto.
    echo          Directorio actual: %CD%
    pause
    exit /b 1
)

echo  [OK] Proyecto encontrado en: %CD%
echo.

REM ── Instalar dependencias ─────────────────────────────────────────
echo  [1/4] Instalando dependencias Python...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)
pip install pillow pyinstaller --quiet
echo  [OK] Dependencias instaladas.
echo.

REM ── Generar icono ─────────────────────────────────────────────────
echo  [2/4] Generando icono NTT DATA...
python build\make_icon.py
if errorlevel 1 (
    echo  [WARN] No se pudo generar el icono. Continuando sin icono...
)
echo.

REM ── Limpiar builds anteriores ─────────────────────────────────────
echo  [3/4] Limpiando builds anteriores...
if exist "dist\MiAplicacion.exe" del /f /q "dist\MiAplicacion.exe"
if exist "dist\MiAplicacion"     rmdir /s /q "dist\MiAplicacion" 2>nul
if exist "__pycache__"           rmdir /s /q "__pycache__" 2>nul
echo  [OK] Limpieza completa.
echo.

REM ── Compilar EXE ─────────────────────────────────────────────────
echo  [4/4] Compilando MiAplicacion.exe con PyInstaller...
echo        (esto puede tardar 2-5 minutos)
echo.
pyinstaller build\legos.spec --noconfirm
if errorlevel 1 (
    echo.
    echo  [ERROR] PyInstaller fallo. Revisa los mensajes anteriores.
    pause
    exit /b 1
)

REM ── Resultado ────────────────────────────────────────────────────
echo.
if exist "dist\MiAplicacion.exe" (
    echo  ╔══════════════════════════════════════════════════════════╗
    echo  ║   BUILD EXITOSO                                          ║
    echo  ╠══════════════════════════════════════════════════════════╣
    for %%F in ("dist\MiAplicacion.exe") do (
        set SIZE=%%~zF
        set /a SIZE_MB=!SIZE! / 1048576
        echo  ║   Archivo: dist\MiAplicacion.exe                         ║
        echo  ║   Tamaño:  !SIZE_MB! MB                                        ║
    )
    echo  ╚══════════════════════════════════════════════════════════╝
    echo.
    echo  Para distribuir, copia junto al .exe:
    echo    - .env  (con las credenciales correctas)
    echo.
    echo  Para ejecutar ahora:
    echo    dist\MiAplicacion.exe
) else (
    echo  [ERROR] El archivo dist\MiAplicacion.exe no fue generado.
)

echo.
pause
