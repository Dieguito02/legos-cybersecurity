# 🔴 Legos Cybersecurity — NTT DATA · OT Red Team Showroom

Dashboard web para demostraciones de ciberseguridad en entornos **OT (Operational Technology)**. Envuelve el toolkit de ataque de consola (`Cyber/demo_attack_ft.py`) en una interfaz gráfica moderna y segura, lista para presentaciones de Red Team en showrooms industriales.

---

## 📋 Tabla de contenidos

- [Descripción general](#descripción-general)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [API REST](#api-rest)
- [Comandos de ataque](#comandos-de-ataque)
- [Autenticación y seguridad](#autenticación-y-seguridad)
- [Generación del ejecutable .exe](#generación-del-ejecutable-exe)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Hoja de ruta](#hoja-de-ruta)

---

## Descripción general

**Legos Cybersecurity** es una aplicación Python/FastAPI que expone una interfaz web (SPA) para ejecutar ataques y demostraciones de ciberseguridad sobre infraestructura OT industrial:

- **Protocolo MQTT** — inyección de órdenes de producción, spoofing de sensores, manipulación de cámaras, ghosting de stock y chaos attacks.
- **Protocolo OPC-UA** — reconocimiento del árbol de nodos del PLC (S7-1500), lectura de variables, escritura de datos falsos, monitoreo en tiempo real.

La aplicación puede ejecutarse en modo desarrollo o empaquetarse como un `.exe` Windows autocontenido (PyInstaller) con apertura automática del navegador.

---

## Arquitectura

```
legos-front/
├── backend/
│   ├── app.py                      ← FastAPI: monta rutas, static y templates
│   ├── core/
│   │   ├── config.py               ← Settings desde .env (dataclass inmutable)
│   │   └── security.py             ← Tokens de sesion HMAC-SHA256
│   ├── routes/
│   │   ├── auth.py                 ← POST /api/login, POST /api/logout, GET /api/user
│   │   ├── api.py                  ← API protegida: comandos, historial, logs SSE
│   │   └── heartbeat.py            ← Watchdog de inactividad + GET /api/heartbeat
│   └── services/
│       ├── command_registry.py     ← Registro declarativo de todos los comandos
│       ├── command_executor.py     ← Ejecucion real (MQTT/OPC-UA), cola de logs
│       ├── history_service.py      ← Historial persistente SQLite
│       ├── network_service.py      ← Estado de red / WiFi
│       └── ot_service.py           ← Adaptador de logica de negocio
│
├── frontend/
│   ├── templates/
│   │   ├── login.html              ← Pantalla de login
│   │   └── dashboard.html          ← Dashboard SPA principal
│   └── static/
│       ├── css/
│       │   ├── theme.css           ← Design tokens NTT DATA
│       │   └── dashboard.css       ← Layout y componentes
│       └── js/
│           └── dashboard.js        ← Navegacion SPA, fetch, toast, SSE
│
├── Cyber/
│   └── demo_attack_ft.py           ← Script original (sin modificar)
│
├── data/
│   └── history.db                  ← Base de datos SQLite (auto-generada)
│
├── .env                            ← Credenciales y configuracion (no versionar)
├── launcher.py                     ← Entrypoint: detecta puerto libre, uvicorn, browser
├── requirements.txt
└── build/
    ├── legos.spec                  ← Spec PyInstaller
    ├── build_windows.bat           ← Script automatico de build (Windows)
    └── make_icon.py                ← Genera build/icon.ico (azul NTT DATA #0072BC)
```

### Flujo de inicio

```
launcher.py
    detecta puerto libre (8000-9000)
    arranca uvicorn en hilo daemon
    TCP probe hasta que el servidor responde (max 30s)
    abre http://127.0.0.1:<puerto> en el navegador

Login  ->  POST /api/login  ->  cookie httpOnly HMAC-SHA256
    ->  Dashboard (acceso protegido por sesion)
```

---

## Requisitos

- **Python 3.10+**
- Conexión de red a los targets OT (broker MQTT y PLC OPC-UA)
- Para generar el `.exe`: Windows nativo con PyInstaller

### Dependencias Python

| Paquete | Uso |
|---|---|
| `fastapi` | Framework web backend |
| `uvicorn[standard]` | Servidor ASGI |
| `jinja2` | Motor de plantillas HTML |
| `python-dotenv` | Carga de `.env` |
| `python-multipart` | Parsing de formularios |
| `itsdangerous` | Base criptográfica (HMAC) |
| `paho-mqtt` | Cliente MQTT |
| `asyncua` | Cliente OPC-UA |
| `opencv-python-headless` | Captura y manipulación de frames de cámara |

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd legos-front

# 2. Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Configuración

Editar el archivo `.env` antes de ejecutar:

```env
# Credenciales de acceso a la interfaz web
APP_USERNAME=admin
APP_PASSWORD=MiPassword123

# Clave secreta para firmar tokens de sesion (HMAC-SHA256)
# Generar con: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=cambia-esto-por-64-caracteres-aleatorios

# Red WiFi del entorno OT (para validacion de conectividad)
WIFI_SSID=nombre_red
WIFI_PASSWORD=clave_wifi

# Broker MQTT
BROKER=192.168.0.10
BROKER_PORT=1883

# PLC / OPC-UA
PLC_ENDPOINT=opc.tcp://192.168.0.1:4840

# Servidor web
HOST=127.0.0.1
PORT=0          # 0 = deteccion automatica de puerto libre

# Sesion
SESSION_COOKIE_NAME=legos_session
SESSION_MAX_AGE_SECONDS=43200   # 12 horas

# Watchdog de inactividad (segundos). 0 = desactivado
INACTIVITY_TIMEOUT=180
```

> **Aviso:** El archivo `.env` contiene credenciales sensibles. Agrégalo a `.gitignore` y nunca lo incluyas en commits públicos.

---

## Ejecución

### Modo desarrollo

```bash
# Opcion A — Launcher completo (detecta puerto y abre el navegador automaticamente)
python launcher.py

# Opcion B — Uvicorn directo con hot-reload
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Luego abrir: `http://127.0.0.1:8000`

### Ejecutable Windows

Ver sección [Generación del ejecutable .exe](#generación-del-ejecutable-exe).

---

## API REST

Todos los endpoints marcados con **Sí** en la columna Auth requieren una cookie de sesión válida (`legos_session`), obtenida al hacer `POST /api/login`.

### Autenticación

| Método | Ruta | Auth | Descripción |
|--------|------|:----:|-------------|
| `POST` | `/api/login` | No | Valida credenciales, devuelve cookie de sesión httpOnly |
| `POST` | `/api/logout` | No | Elimina la cookie de sesión |
| `GET` | `/api/user` | Sí | Devuelve el nombre del usuario autenticado |

### Sistema

| Método | Ruta | Auth | Descripción |
|--------|------|:----:|-------------|
| `GET` | `/api/status` | No | Estado del servicio, broker y endpoint OPC-UA configurados |
| `GET` | `/api/heartbeat` | No | Probe de actividad para el watchdog de inactividad |
| `GET` | `/api/network` | Sí | Estado de conectividad de red / WiFi |

### Comandos

| Método | Ruta | Auth | Descripción |
|--------|------|:----:|-------------|
| `GET` | `/api/commands` | Sí | Lista todos los comandos disponibles |
| `GET` | `/api/commands/by-category` | Sí | Comandos agrupados por categoría |
| `POST` | `/api/commands/{command_id}/execute` | Sí | Ejecuta un comando (body JSON: `{"params": {...}}`) |
| `POST` | `/api/commands/{exec_id}/cancel` | Sí | Cancela una operación en background |
| `GET` | `/api/operations/active` | Sí | Lista las operaciones en background activas |

### Historial

| Método | Ruta | Auth | Descripción |
|--------|------|:----:|-------------|
| `GET` | `/api/history` | Sí | Historial de ejecuciones (`?limit=50&offset=0`) |
| `GET` | `/api/history/stats` | Sí | Estadísticas agregadas de ejecución |
| `GET` | `/api/history/{exec_id}` | Sí | Detalle de una ejecución específica |
| `DELETE` | `/api/history` | Sí | Limpia el historial completo |

### Logs

| Método | Ruta | Auth | Descripción |
|--------|------|:----:|-------------|
| `GET` | `/api/logs/stream` | Sí | Stream de logs en tiempo real via SSE (`text/event-stream`) |
| `GET` | `/api/logs/recent` | Sí | Últimas 200 entradas de log (no streaming) |

---

## Comandos de ataque

Los comandos se registran en `backend/services/command_registry.py` y están organizados por categoría y nivel de peligro: `low` / `medium` / `high` / `critical`.

Los comandos con fondo en background (`background: true`) pueden cancelarse con `POST /api/commands/{exec_id}/cancel`.

### MQTT · L1 — Órdenes de producción

| ID | Label | Descripción | Nivel |
|----|-------|-------------|:-----:|
| `mqtt_order_red` | Order RED | Publica orden de producción RED al bus MQTT. Inicia ciclo HBW→VGR→MPO→SLD→DPS (~2-3 min) | medium |
| `mqtt_order_blue` | Order BLUE | Publica orden de producción BLUE | medium |
| `mqtt_order_white` | Order WHITE | Publica orden de producción WHITE | medium |
| `mqtt_ptu_dance` | PTU Dance | Camera misdirection: barrido lateral → cámara al techo 10 s (ventana ciega) → retorno al centro | medium |

### MQTT · L3 — Spoofing de sensores

| ID | Label | Descripción | Nivel |
|----|-------|-------------|:-----:|
| `mqtt_sensor_spoof` | Sensor Spoof | Inyecta lecturas nominales falsas (22.5 °C) en `i/bme680` a 800 ms, enterrando el sensor real | high |
| `mqtt_sensor_alarm` | Sensor Alarm | Inyecta 87 °C crítico sostenido en `i/bme680`. Dispara protocolo de evacuación en el HMI | critical |

### MQTT · L4 — Manipulación de estado de planta

| ID | Label | Descripción | Nivel |
|----|-------|-------------|:-----:|
| `mqtt_chaos_busy` | Chaos Busy | Marca simultáneamente todas las estaciones (HBW/VGR/MPO/SLD) como BUSY en loop. Fábrica paralizada | critical |
| `mqtt_ghost_stock` | Ghost Stock | Publica 9 piezas fantasma en `f/i/stock`. ERP y dashboard ven rack lleno; stock real ignorado | high |
| `mqtt_reset_state` | Reset State | Detiene todos los ataques background y envía estado IDLE a todas las estaciones | low |

### MQTT · L5 — Manipulación de cámara

| ID | Label | Descripción | Nivel |
|----|-------|-------------|:-----:|
| `mqtt_fire_loop` | Fire Loop | Publica frames de incendio base64 en `i/cam` a 1 Hz. El operador ve fuego → evacuación | critical |
| `mqtt_freeze_frame` | Freeze Frame | Captura un frame real y lo republica en loop. La cámara parece funcionar pero está congelada | critical |

### MQTT · L6 — Reconocimiento y takeover

| ID | Label | Descripción | Nivel | Parámetros |
|----|-------|-------------|:-----:|------------|
| `mqtt_eavesdrop` | Eavesdrop | Suscripción pasiva al wildcard `#` durante N segundos. Mapea topics, NFC IDs, órdenes y sensores sin publicar nada | low | `seconds` (default: 12) |
| `mqtt_takeover` | Takeover | Ransomware-style: 5 ataques encadenados en menos de 20 s (chaos busy + sensor alarm + ghost stock + fake shipped + fire loop) | critical | — |

### OPC-UA — Reconocimiento y explotación del PLC

| ID | Label | Descripción | Nivel | Parámetros |
|----|-------|-------------|:-----:|------------|
| `opcua_discover` | Discover | Recorre el árbol de nodos del S7-1500 sin autenticación (anónimo, sin TLS). Hasta N niveles de profundidad | low | `max_depth` (default: 6) |
| `opcua_browse` | Browse | Enumera namespace y lee variables clave del PLC (setup buttons, SSC thresholds, error flags, FW version) | low | — |
| `opcua_read` | Read Plant Snapshot | Snapshot completo del estado interno del PLC con todas las variables de `TARGETS_READ` | low | — |
| `opcua_inspect` | Inspect Variable | Examina esquema y tipo de una variable OPC-UA (browse name, data type, access level, valor actual) | low | `target` (requerido) |
| `opcua_ghost_real` | Ghost Real | Sobreescribe `Rack_Workpiece` en el PLC con 9 piezas fantasma. Afecta al HMI oficial y al scheduler del controlador | critical | — |
| `opcua_save_snapshot` | Save Snapshot | Guarda el inventario real del rack HBW a un archivo JSON antes del ataque | low | — |
| `opcua_restore_snapshot` | Restore Snapshot | Restaura el inventario del rack HBW desde el snapshot guardado. Reescribe el PLC con los valores originales | high | — |
| `opcua_trigger_park` | Trigger Park | Escribe `True` en `gtyp_Setup.x_Park_Position`. Mueve físicamente todas las estaciones a posición de parking | high | — |
| `opcua_monitor` | Monitor Variables | Suscripción OPC-UA en tiempo real a ~40 variables del PLC. Muestra cada cambio con timestamp | low | `duration` (default: 60) |

### CONTROL

| ID | Label | Descripción | Nivel |
|----|-------|-------------|:-----:|
| `ctrl_stop_all` | Stop All Background Operations | Detiene todos los ataques en background: camera hijack, sensor spoof, state injections | low |

---

## Autenticación y seguridad

- **Sesión basada en cookie httpOnly** firmada con HMAC-SHA256 usando `SECRET_KEY`.
- La cookie (`legos_session`) tiene duración configurable (`SESSION_MAX_AGE_SECONDS`, default 12 h) y la flag `SameSite=Lax`.
- Las credenciales se comparan en tiempo constante para prevenir timing attacks.
- **Watchdog de inactividad**: si el frontend no envía heartbeat en `INACTIVITY_TIMEOUT` segundos, el proceso se cierra automáticamente (útil en demos públicas).
- Para producción, rotar `SECRET_KEY` con un valor de 64 caracteres aleatorios:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Generación del ejecutable .exe

> **Importante:** PyInstaller genera binarios para la plataforma donde se ejecuta. Debes correr el build **desde Windows nativo**, no desde WSL.

### Pasos (desde Windows)

**Opción A — Script automático (recomendado)**

```bat
rem Copiar proyecto a Windows (desde WSL):
cp -r /home/dieguito/demos/legos-front /mnt/c/Projects/legos-front

rem Desde CMD o PowerShell en Windows:
cd C:\Projects\legos-front
build\build_windows.bat
```

**Opción B — Manual**

```bat
cd C:\Projects\legos-front
pip install -r requirements.txt pillow pyinstaller
python build\make_icon.py
pyinstaller build\legos.spec --noconfirm
```

### Resultado

```
dist\
└── MiAplicacion.exe    <- ejecutable Windows autocontenido con icono NTT DATA azul
```

### Notas

- El archivo `.env` se incluye dentro del bundle. Para cambiar credenciales en producción, colocar un `.env` junto al `.exe` — tiene precedencia sobre el interno.
- `console=False` en el spec elimina la ventana de consola para el usuario final.
- El icono (`build/icon.ico`) se genera automáticamente si no existe. Para regenerarlo: `python build/make_icon.py`.

---

## Estructura del proyecto

| Archivo / Directorio | Descripción |
|---|---|
| `backend/app.py` | Aplicación FastAPI principal |
| `backend/core/config.py` | Configuración desde `.env` (dataclass inmutable) |
| `backend/core/security.py` | Tokens HMAC-SHA256, validación de credenciales |
| `backend/routes/auth.py` | Rutas de autenticación |
| `backend/routes/api.py` | Rutas de API protegidas |
| `backend/routes/heartbeat.py` | Watchdog de inactividad |
| `backend/services/command_registry.py` | Registro declarativo de comandos |
| `backend/services/command_executor.py` | Ejecución real de comandos MQTT/OPC-UA |
| `backend/services/history_service.py` | Historial persistente en SQLite |
| `backend/services/network_service.py` | Estado de red y WiFi |
| `backend/services/ot_service.py` | Adaptador de lógica de negocio |
| `frontend/templates/login.html` | Pantalla de login |
| `frontend/templates/dashboard.html` | Dashboard SPA principal |
| `frontend/static/css/theme.css` | Design tokens NTT DATA |
| `frontend/static/css/dashboard.css` | Estilos del dashboard |
| `frontend/static/js/dashboard.js` | Lógica JavaScript (navegación, SSE, toast) |
| `Cyber/demo_attack_ft.py` | Script de ataque original (sin modificar) |
| `data/history.db` | Base de datos SQLite de historial (auto-generada) |
| `.env` | Variables de entorno y credenciales |
| `launcher.py` | Entrypoint con detección de puerto y apertura de browser |
| `requirements.txt` | Dependencias Python |
| `build/legos.spec` | Configuración PyInstaller |
| `build/build_windows.bat` | Script automático de build para Windows |
| `build/make_icon.py` | Generador del icono NTT DATA |
| `GUIA_BUILD.md` | Guía detallada de build y despliegue |

---

## Hoja de ruta

### Fase 1 — Base funcional (completada)
- Estructura backend/frontend separados con FastAPI.
- Login con sesión segura (cookie httpOnly, HMAC-SHA256).
- Dashboard con sidebar, navegación SPA, KPIs y consola de logs.
- Launcher con detección de puerto libre.
- Spec de PyInstaller para generar `.exe` Windows.

### Fase 2 — Integración de lógica existente
- Envolver `Cyber/demo_attack_ft.py` completamente en `OTService`.
- Ejecución en background con asyncio/threading para procesos largos.
- WebSocket o SSE para streaming de logs en tiempo real.

### Fase 3 — Interactividad completa
- Formularios específicos por escenario (target IP, parámetros MQTT, etc.).
- Barra de progreso para operaciones largas.
- Tabla de resultados por comando.
- Historial persistente de sesión.

### Fase 4 — Hardening y producción
- HTTPS local con certificado autofirmado.
- Rate limiting en `/api/login`.
- Expiración y renovación automática de sesión.
- Logs de auditoría persistentes.
- Rotación de `SECRET_KEY` desde variables de entorno del SO.

---

> Este proyecto es una herramienta de demostración para uso exclusivo en entornos de laboratorio controlados.  
> No usar contra infraestructura real sin autorización explícita.
