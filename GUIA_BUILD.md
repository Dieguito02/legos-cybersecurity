# NTT DATA · OT Red Team Showroom — Guía de Build y Despliegue

## 1. Arquitectura final

```
project/
├── backend/
│   ├── __init__.py
│   ├── app.py                  ← FastAPI app (monta static + templates + rutas)
│   ├── core/
│   │   ├── config.py           ← Settings desde .env
│   │   └── security.py         ← Tokens de sesión HMAC-SHA256, validación de credenciales
│   ├── routes/
│   │   ├── auth.py             ← POST /api/login · POST /api/logout · GET /api/user
│   │   └── api.py              ← GET /api/status · GET /api/commands · etc.
│   └── services/
│       └── ot_service.py       ← Wrapper de la lógica de negocio (adaptador)
│
├── frontend/
│   ├── templates/
│   │   ├── login.html          ← Pantalla de Login
│   │   └── dashboard.html      ← Dashboard principal
│   └── static/
│       ├── css/
│       │   ├── theme.css       ← Design tokens NTT DATA
│       │   └── dashboard.css   ← Layout y componentes
│       └── js/
│           └── dashboard.js    ← Lógica SPA (navegación, fetch, toast)
│
├── Cyber/
│   └── demo_attack_ft.py       ← Script original (sin modificar)
│
├── .env                        ← Credenciales (nunca versionar)
├── launcher.py                 ← Arranque: detecta puerto libre → uvicorn → abre browser
├── requirements.txt            ← Dependencias Python
└── build/
    └── legos.spec              ← Configuración PyInstaller
```

---

## 2. Mapa consola → interfaz gráfica

| Consola original           | Componente web                          |
|----------------------------|-----------------------------------------|
| Menú de opciones numéricas | Sidebar de navegación + cards de acción |
| `input()`                  | `<input>` / `<select>` / formularios    |
| `print()` resultados       | Tablas, `result-box`, JSON viewer       |
| `print()` logs             | Consola visual (`log-console`)          |
| Confirmaciones de consola  | Modales / toast notifications           |
| Proceso largo              | Botón con spinner + estado deshabilitado|
| Salir del programa         | Botón "Cerrar sesión" + `POST /logout`  |
| Escenarios SC-01/02/03     | Cards en vista "Escenarios"             |

---

## 3. Endpoints REST implementados

| Método | Ruta               | Auth | Descripción                          |
|--------|--------------------|------|--------------------------------------|
| POST   | /api/login         | No   | Valida credenciales, crea sesión      |
| POST   | /api/logout        | No   | Elimina cookie de sesión             |
| GET    | /api/user          | Sí   | Devuelve usuario autenticado          |
| GET    | /api/status        | No   | Estado del servicio backend           |
| GET    | /api/commands      | Sí   | Lista de acciones disponibles         |
| POST   | /api/start-process | Sí   | Inicia proceso                        |
| POST   | /api/stop-process  | Sí   | Detiene proceso                       |
| GET    | /api/logs          | Sí   | Registro de eventos                   |
| GET    | /api/documentation | Sí   | Documentación del sistema             |

---

## 4. Instalación de dependencias

```bash
pip install -r requirements.txt
```

---

## 5. Configuración de credenciales

Editar `.env` antes de ejecutar:

```env
APP_USERNAME=admin
APP_PASSWORD=MiPassword123
SECRET_KEY=cambia-esto-por-64-caracteres-aleatorios
HOST=127.0.0.1
PORT=0          # 0 = detectar automáticamente un puerto libre
```

Generar un SECRET_KEY seguro:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 6. Ejecución en modo desarrollo

```bash
# Opción A: launcher completo (abre navegador automáticamente)
python launcher.py

# Opción B: uvicorn directo (sin abrir navegador)
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# Luego abrir:
# http://127.0.0.1:8000
```

---

## 7. Generación del ejecutable (.exe)

### ⚠️ IMPORTANTE — WSL vs Windows

**PyInstaller genera binarios para la plataforma donde se ejecuta.**  
Si corres PyInstaller desde WSL (Linux), obtienes un ELF Linux, **no un .exe**.  
Para generar `MiAplicacion.exe` debes ejecutar el build **desde Windows nativo**.

---

### Pasos para generar el .exe (desde Windows)

#### Opción A — Script automático (recomendado)

1. Copia el proyecto a una ruta Windows (p.ej. `C:\Projects\legos-front`)  
   Desde WSL puedes acceder a tus discos en `/mnt/c/`:
   ```bash
   cp -r /home/dieguito/demos/legos-front /mnt/c/Projects/legos-front
   ```

2. Abre **CMD** o **PowerShell** en Windows y ejecuta:
   ```bat
   cd C:\Projects\legos-front
   build\build_windows.bat
   ```
   El script instala dependencias, genera el icono y compila el .exe automáticamente.

#### Opción B — Manual

```bat
cd C:\Projects\legos-front
pip install -r requirements.txt pillow pyinstaller
python build\make_icon.py
pyinstaller build\legos.spec --noconfirm
```

### Resultado

```
dist\
└── MiAplicacion.exe    ← ejecutable Windows con icono NTT DATA azul
```

### Icono

El icono se genera con `build/make_icon.py` usando Pillow.  
Produce `build/icon.ico` con 6 tamaños (16, 32, 48, 64, 128, 256 px)  
en el azul corporativo NTT DATA (`#0072BC`).

Para regenerar el icono manualmente:
```bash
python build/make_icon.py
```

### Notas importantes

- El archivo `.env` se incluye dentro del bundle.  
  Para cambiar credenciales en producción, colocar un `.env` junto al `.exe` —
  tiene precedencia sobre el `.env` interno.
- `console=False` en el spec elimina la ventana de consola para el usuario final.
- Si se usa UPX para comprimir, instalar UPX y asegurarse de que está en el PATH de Windows.
- El spec auto-genera el icono si `build/icon.ico` no existe al momento del build.

---

## 8. Flujo de ejecución del .exe

```
Usuario ejecuta MiAplicacion.exe
        ↓
launcher.py detecta puerto libre (8000–9000)
        ↓
Arranca uvicorn backend.app:app en segundo plano
        ↓
Espera hasta que el servidor responda (TCP probe, max 30s)
        ↓
Abre http://127.0.0.1:<puerto> en el navegador predeterminado
        ↓
Pantalla de Login (credenciales desde .env)
        ↓
POST /api/login → cookie de sesión HMAC-SHA256 httpOnly
        ↓
Dashboard principal (acceso protegido)
```

---

## 9. Plan de migración por fases

### Fase 1 — Base funcional ✅ (completada)
- Estructura de proyecto backend/frontend separados.
- FastAPI con rutas de autenticación y API REST básica.
- Login con sesión segura (cookie httpOnly, HMAC-SHA256).
- Dashboard con sidebar, navegación SPA, KPIs, consola de logs.
- Launcher con detección de puerto libre y apertura de navegador.
- Spec de PyInstaller.

### Fase 2 — Integración de lógica existente
- Envolver `Cyber/demo_attack_ft.py` en `OTService`.
- Exponer cada comando de consola como endpoint específico.
- Añadir ejecución en background (asyncio / threading) para procesos largos.
- Agregar WebSocket o SSE para streaming de logs en tiempo real.

### Fase 3 — Interactividad completa
- Formularios específicos por escenario (target IP, parámetros MQTT, etc.).
- Progreso de operaciones con barra de carga.
- Tabla de resultados por comando.
- Historial persistente de sesión.

### Fase 4 — Hardening y producción
- Rotar SECRET_KEY desde variables de entorno del SO.
- HTTPS local con certificado autofirmado.
- Rate limiting en `/api/login`.
- Expiración y renovación de sesión.
- Logs de auditoría persistentes.

---

## 10. Archivos nuevos generados

| Archivo                            | Descripción                               |
|------------------------------------|-------------------------------------------|
| `backend/__init__.py`              | Paquete Python                            |
| `backend/app.py`                   | Aplicación FastAPI principal              |
| `backend/core/__init__.py`         | Paquete                                   |
| `backend/core/config.py`           | Configuración desde .env                  |
| `backend/core/security.py`         | Tokens HMAC, validación de credenciales   |
| `backend/routes/__init__.py`       | Paquete                                   |
| `backend/routes/auth.py`           | Rutas de autenticación                    |
| `backend/routes/api.py`            | Rutas de API protegidas                   |
| `backend/services/__init__.py`     | Paquete                                   |
| `backend/services/ot_service.py`   | Adaptador de lógica de negocio            |
| `frontend/templates/login.html`    | Pantalla de Login                         |
| `frontend/templates/dashboard.html`| Dashboard principal                        |
| `frontend/static/css/theme.css`    | Design tokens NTT DATA                    |
| `frontend/static/css/dashboard.css`| Estilos del dashboard                     |
| `frontend/static/js/dashboard.js`  | Lógica JavaScript del dashboard           |
| `.env`                             | Variables de entorno (credenciales)       |
| `launcher.py`                      | Launcher con apertura automática          |
| `requirements.txt`                 | Dependencias Python actualizadas          |
| `build/legos.spec`                 | Configuración PyInstaller                 |
| `GUIA_BUILD.md`                    | Esta guía                                 |

## 11. Archivos originales sin modificar

| Archivo                      | Estado    |
|------------------------------|-----------|
| `Cyber/demo_attack_ft.py`    | Intacto   |
| `Cyber/requirements.txt`     | Intacto   |
| `ShowroomCyberDashboard 1.html` | Intacto (referencia de diseño) |
