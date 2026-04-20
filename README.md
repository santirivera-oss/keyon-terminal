# KEYON Terminal Pro v2

Sistema de reconocimiento facial nativo para control de asistencia escolar, desplegado sobre hardware embebido Raspberry Pi Zero 2W, con integración directa al ecosistema Firebase del proyecto Keyon Access System.

**Versión actual:** v2.0.4-dev  
**Última actualización:** 19 de abril de 2026  
**Estado:** Production-ready (auto-start validado con reboot)

---

## Tabla de contenidos

- [Resumen ejecutivo](#resumen-ejecutivo)
- [Contexto del proyecto](#contexto-del-proyecto)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Hardware](#hardware)
- [Software stack](#software-stack)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Pipeline de reconocimiento facial](#pipeline-de-reconocimiento-facial)
- [Modelo de datos](#modelo-de-datos)
- [Integración con Firebase](#integración-con-firebase)
- [Monitoreo remoto (heartbeat)](#monitoreo-remoto-heartbeat)
- [Arranque automático (systemd)](#arranque-automático-systemd)
- [Scripts disponibles](#scripts-disponibles)
- [Guía de uso](#guía-de-uso)
- [Métricas validadas](#métricas-validadas)
- [Bitácora de desarrollo](#bitácora-de-desarrollo)
- [Consideraciones de seguridad y LFPDPPP](#consideraciones-de-seguridad-y-lfpdppp)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Roadmap](#roadmap)
- [Autor y licencia](#autor-y-licencia)

---

## Resumen ejecutivo

Keyon Terminal Pro v2 es la **evolución embebida** del sistema Keyon Access System, concebida como kiosco físico autónomo para el control de acceso y asistencia en planteles educativos públicos. A diferencia de la versión web v1 que opera en PCs con navegador Chromium ejecutando face-api.js, la Terminal Pro v2 implementa el reconocimiento facial completamente de forma **nativa en Python + OpenCV + modelos ONNX**, directamente sobre un SBC ARM de bajo consumo y bajo costo.

La terminal opera como unidad independiente con:
- Detección y reconocimiento facial locales (sin dependencia de servidor externo)
- Base de datos local SQLite para descriptores faciales
- Sincronización de registros de asistencia al Firestore compartido con el sistema web
- Monitoreo remoto vía heartbeat a Firestore cada 5 minutos
- Arranque automático al bootear vía systemd service
- Auto-recuperación ante crashes (restart on failure)
- Logs estructurados con rotación diaria (30 días de retención)

El sistema fue validado funcionalmente el **19 de abril de 2026** con registro end-to-end completo y posteriormente hardening de production-grade con systemd auto-start validado post-reboot.

**Hitos clave:**
- `21:11:39` - Primer documento escrito a producción (doc id: `Cc5sleYZoGK3J8w39xBo`)
- `21:22:00` - Badge "Terminal" validado en panel admin web (v3.15.4)
- `23:29:05` - Primer heartbeat a `terminal_status` validado
- `23:40:40` - Auto-start via systemd validado post-reboot (49s boot → operativa)
- `00:XX:00` - Panel "Terminales" deployed en web (v3.15.5)

---

## Contexto del proyecto

### Proyecto matriz: Keyon Access System

Keyon es un sistema integral de control de asistencia escolar con biometría facial y códigos QR dinámicos TOTP, en **operación en producción** en el CBTis No. 001 de Fresnillo, Zacatecas. El sistema completo incluye:

- **Web PWA** (React + TypeScript + Firebase) — panel administrativo, pase de lista para profesores, interfaces para alumnos
- **App móvil React Native Expo** — para padres de familia con notificaciones push
- **Cloud Functions** desplegadas en `us-central1` — notificaciones y lógica serverless
- **Módulo ESP32 v8.3 PIR** — sensores PIR + VL53L0X + buzzer + pantalla TFT ILI9341 con comunicación WebSocket
- **Cumplimiento LFPDPPP completo (Bloque A)** — cifrado AES-GCM-256 + PBKDF2 150,000 iteraciones, aviso integral de privacidad, derechos ARCO
- **Panel admin "Terminales"** (v3.15.5) — monitoreo en tiempo real de terminales físicas conectadas

### Registro oficial

- **Número de registro CNPyPE 2026:** 26-AT2099
- **Categoría:** Alumno-Tecnológico
- **Plantel:** CBTis No. 001, Fresnillo, Zacatecas
- **Fase:** Nacional (1er lugar estatal CNPyPE 2026)
- **Repositorio terminal:** [github.com/santirivera-oss/keyon-terminal](https://github.com/santirivera-oss/keyon-terminal) (público)
- **Repositorio web:** [github.com/santirivera-oss/SCANER-V3](https://github.com/santirivera-oss/SCANER-V3) (privado)

---

## Arquitectura del sistema

```
┌──────────────────────────────────────────────────────────────┐
│                    ECOSISTEMA KEYON                          │
│                                                              │
│  ┌─────────────────┐              ┌──────────────────────┐   │
│  │  Sistema Web    │              │  Terminal Pro v2     │   │
│  │  v3.15.5        │              │  v2.0.4-dev          │   │
│  │                 │              │                      │   │
│  │  React+TS+PWA   │              │  Python+OpenCV       │   │
│  │  Firebase Host  │              │  YuNet + SFace       │   │
│  │  Chromium       │              │  SQLite local        │   │
│  │  face-api.js    │              │  systemd auto-start  │   │
│  │                 │              │  Heartbeat 5min      │   │
│  │  Panel admin    │◀──────▶────▶│                      │   │
│  │  + vista        │              │                      │   │
│  │  "Terminales"   │              │                      │   │
│  └────────┬────────┘              └───────────┬──────────┘   │
│           │                                    │              │
│           └──────────────┬─────────────────────┘              │
│                          │                                    │
│                          ▼                                    │
│           ┌──────────────────────────┐                        │
│           │  Firebase Firestore      │                        │
│           │  (scanner-v3)            │                        │
│           │                          │                        │
│           │  44 colecciones:         │                        │
│           │  - alumnos               │                        │
│           │  - ingresos_cbtis        │  ← escriben ambos    │
│           │  - terminal_status       │  ← solo Pi            │
│           │  - biometricos_seguros   │                        │
│           │  - consentimientos       │                        │
│           │  - ... (40 más)          │                        │
│           └──────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

### Flujo completo en producción

```
BOOT → SYSTEMD → PYTHON → FIREBASE ─┬─► HEARTBEAT cada 5min
                                     │   (terminal_status)
                                     │
                                     └─► LOOP PRINCIPAL
                                         │
                                         ├─► Captura (ffmpeg/C270)
                                         ├─► Detección (YuNet ONNX)
                                         ├─► Alineación + Embedding (SFace)
                                         ├─► Match contra SQLite local
                                         └─► Si match válido:
                                             ├─► Registro local SQLite
                                             └─► Escribe ingresos_cbtis
                                                 (+ anti-duplicados 60s)
```

---

## Hardware

### Placa principal

- **Modelo:** Raspberry Pi Zero 2W Rev 1.0
- **Procesador:** Broadcom BCM2710A1, núcleo ARM Cortex-A53 quad-core @ 1 GHz (ARMv8, 64-bit)
- **RAM:** 512MB LPDDR2 SDRAM (416 MB efectivos disponibles tras reserva GPU)
- **Memoria swap:** 415 MB auxiliar en microSD
- **Almacenamiento:** microSD ADATA Premier 128GB UHS-I V10 A1 (114 GB útiles tras formateo, ~105 GB libres en uso)
- **Conectividad:** WiFi 802.11 b/g/n 2.4 GHz + Bluetooth 4.2/BLE
- **Interfaces activas:** SPI (`/dev/spidev0.0`, `/dev/spidev0.1`), I2C (`/dev/i2c-1`, `/dev/i2c-2`)
- **Consumo en operación:** ~2-3W
- **Temperatura típica:** 42-48°C idle, 50-55°C bajo carga continua (umbral throttling a 80°C)

### Periféricos actuales

- **Cámara:** Logitech C270 HD Webcam (VID 046d, PID 0825) vía cable OTG Soku V8 Micro USB
  - Resolución usada: 640x480 YUYV @ 30 fps
  - Detección automática por driver UVC estándar Linux
- **Fuente de poder:** Tecneu 5V 3A con botón ON/OFF

### Periféricos pendientes (en proceso)

- **Pantalla:** 3.5" SPI ILI9486 480x320 táctil (pendiente soldar headers)
- **Audio:** 2x PAM8403 + 2x bocinas 50mm 4Ω (pendiente soldar headers)
- **Headers GPIO:** compra pendiente Steren Fresnillo

### Presupuesto de hardware

| Componente | Costo (MXN) | Estado |
|---|---|---|
| Raspberry Pi Zero 2W | 806.44 | ✅ En uso |
| Fuente 5V 3A Tecneu | 139.56 | ✅ En uso |
| microSD ADATA 128GB | 378.00 | ✅ En uso |
| Cámara Logitech C270 | 486.00 | ✅ En uso |
| Pantalla SPI 3.5" ILI9486 | 474.05 | ⏳ Pendiente headers |
| Cable OTG Soku V8 | 159.99 | ✅ En uso |
| 2x PAM8403 | 84.36 | ⏳ Pendiente headers |
| 2x Bocinas 50mm 4Ω | 141.55 | ⏳ Pendiente headers |
| **Subtotal hardware** | **2,669.95** | |
| Headers 40 pines (Steren) | ~35.00 | 🔜 Lunes |
| Adaptador mini-HDMI (Steren) | ~120.00 | 🔜 Lunes |
| Cautín/estaño (prestado CBTis) | 0.00 | 🔜 Lunes |
| Case 3D impreso | ~400.00 | 🔜 Semana |
| **Total proyectado** | **~3,225.00** | |

### Comparativo con soluciones comerciales

| Sistema | Precio | Observación |
|---|---|---|
| **Keyon Terminal Pro v2** | **$3,225 MXN** | Nativo Python, código abierto, cumple LFPDPPP |
| Hikvision DS-K1T343MWX | $4,000 – $8,000 MXN | Proprietario, sin compliance LFPDPPP México |
| ZKTeco SpeedFace-V5L | $3,000 – $5,000 MXN | Proprietario, sin integración Firebase |

---

## Software stack

### Sistema operativo

- **Debian GNU/Linux 13 "Trixie"** (rama estable 2025-2026)
- **Kernel:** Linux 6.12.75+rpt-rpi-v8 (marzo 2026)
- **Arquitectura:** aarch64 (ARM64)
- **Gestor de servicios:** systemd (con auto-start de `keyon-terminal.service`)

### Runtime y librerías Python

- **Python 3.13.5** (pre-instalado en Raspberry Pi OS Lite)
- **pip3** 25.1.1
- **numpy** 2.4.4
- **opencv-python-headless** 4.13.0.92
- **firebase-admin** 7.4.0
- **google-cloud-firestore** 2.27.0
- **sqlite3** 3.46.1 (CLI + biblioteca estándar Python)

### Modelos de inteligencia artificial

- **Detección:** YuNet `face_detection_yunet_2023mar.onnx`
  - Fuente: OpenCV Model Zoo oficial
  - Arquitectura: MobileNetV2 cuantizada
  - Tamaño: 228 KB
  - Precisión validada: 92-95% confianza en rostros frontales

- **Reconocimiento:** SFace `face_recognition_sface_2021dec.onnx`
  - Fuente: OpenCV Model Zoo oficial
  - Arquitectura: ResNet-50 optimizada
  - Tamaño: 37 MB
  - Output: embedding 128-dim float32 (512 bytes)

### Herramientas

- **Git** 2.47.3
- **tmux** 3.5a
- **ffmpeg** 7.1.3
- **v4l-utils** (diagnóstico cámara)

### DevOps / Production

- **systemd service** con auto-start al boot
- **Restart on failure** con backoff automático
- **Logs rotativos diarios** (30 días retención)
- **Límite de memoria** 400MB
- **Límite de CPU** 90%
- **Journal de systemd** para logs del servicio

---

## Estructura del repositorio

```
keyon-terminal/                          github.com/santirivera-oss/keyon-terminal
├── README.md                            Este archivo (documentación completa)
├── .gitignore                           Protege credenciales + logs + BD
│
├── db/                                  [IGNORED] BD SQLite con biométricos
│   └── keyon.db
│
├── logs/                                [IGNORED] Logs rotativos del kiosco
│   └── kiosco.log
│
├── modelos/
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
│
├── systemd/                             Service file para auto-start
│   └── keyon-terminal.service
│
├── docs/                                Documentación adicional (TBD)
│
└── scripts/
    ├── db_init.py                       Inicializar schema de BD
    ├── deteccion_test.py                Prueba Haar Cascade (legacy)
    ├── detectar_yunet.py                Detección moderna YuNet
    ├── reconocer_sface.py               Comparación 1:1 entre rostros
    ├── registrar.py                     Enroll de alumno
    ├── identificar.py                   Identificación 1:N
    ├── firebase_test.py                 Test lectura Firestore
    ├── firebase_write.py                Test escritura Firestore (legacy)
    ├── firebase_cleanup_terminal.py     Limpieza de registros test
    └── terminal_main.py                 🎯 Kiosco loop principal v2.0.3-dev
```

---

## Pipeline de reconocimiento facial

### Etapa 1 — Captura de imagen

```bash
ffmpeg -f v4l2 -video_size 640x480 -i /dev/video0 \
       -vf "select='eq(n,5)'" \
       -frames:v 1 -update 1 -y /tmp/keyon_frame.jpg
```

El filtro `select='eq(n,5)'` captura el frame 5 para dar tiempo al sensor C270 de auto-calibrar exposición. Timeout robusto de 10 segundos con retry backoff.

### Etapa 2 — Detección con YuNet

```python
detector = cv2.FaceDetectorYN.create(
    "face_detection_yunet_2023mar.onnx",
    "",
    (640, 480),
    score_threshold=0.6
)

_, rostros = detector.detect(imagen)
```

Retorna bounding boxes + 5 landmarks + confianza por rostro.

### Etapa 3 — Alineación facial

```python
rostro_alineado = reconocedor.alignCrop(imagen, rostro)
```

SFace usa los 5 landmarks para rotar y escalar el rostro a formato canónico 112x112 RGB.

### Etapa 4 — Generación de embedding

```python
embedding = reconocedor.feature(rostro_alineado)
# embedding.shape == (1, 128), dtype float32, 512 bytes
```

### Etapa 5 — Comparación

**Distancia coseno** (umbral match OpenCV oficial: `> 0.363`)  
**Distancia L2** (umbral match OpenCV oficial: `< 1.128`)

Doble validación: ambas métricas deben superar umbral simultáneamente.

### Etapa 6 — Anti-duplicados

```python
if (datetime.now() - ultimo_registro[matricula]).total_seconds() < 60:
    return "cooldown"  # no registra
```

---

## Modelo de datos

### SQLite local (`db/keyon.db`)

#### Tabla `alumnos`

```sql
CREATE TABLE alumnos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    grupo TEXT,
    matricula TEXT UNIQUE,
    embedding BLOB NOT NULL,           -- 512 bytes (128 float32)
    fecha_registro TEXT DEFAULT (datetime('now', 'localtime')),
    activo INTEGER DEFAULT 1
);
```

#### Tabla `asistencias`

```sql
CREATE TABLE asistencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id INTEGER NOT NULL,
    timestamp TEXT DEFAULT (datetime('now', 'localtime')),
    tipo TEXT DEFAULT 'entrada',
    score_cosine REAL,
    score_l2 REAL,
    sincronizado_firebase INTEGER DEFAULT 0,
    FOREIGN KEY (alumno_id) REFERENCES alumnos (id)
);
```

### Firestore (scanner-v3)

#### Colección `ingresos_cbtis` (compartida con sistema web)

Schema completo compatible con sistema web v3.15.5, enriquecido con campos específicos de terminal:

```typescript
{
  // Campos estándar del web
  tipoPersona: "Alumno",
  nombre: string,
  identificador: string,              // matrícula
  aula: string,
  grado: string,                      // "4°B"
  grupo: string,
  turno: "matutino" | "vespertino",
  estadoLlegada: "puntual" | "retardo" | "tarde" | null,
  tipoRegistro: "Ingreso" | "Salida",
  fecha: "YYYY-MM-DD",
  hora: "HH:MM:SS",
  modo: "facial",
  timestamp: ISO_string,
  fotoUrl: null,
  escuela: "CBTis No. 001",
  
  // Campos específicos terminal
  origen: "terminal_pi",              // ⭐ discriminador para badge admin
  terminalId: string,
  dispositivo: "Raspberry Pi Zero 2W",
  metodoVerificacion: "facial_local_terminal",
  scoreCosine: number,
  scoreL2: number,
  procesadoEnDispositivo: true,
  sincronizadoFirebase: true,
  versionTerminal: "2.0.3-dev"
}
```

#### Colección `terminal_status` (creada para v2)

Heartbeat/estado de terminales conectadas. Un documento por terminal (doc.id = terminalId):

```typescript
{
  terminalId: string,                  // ej "keyon-pi-zero2w-01"
  dispositivo: string,
  estado: "online" | "offline",
  ultimoHeartbeat: Timestamp,          // server Google
  ultimoHeartbeatLocal: string,        // ISO 8601
  temperaturaCpu: number,              // celsius
  uptimeSegundos: number,
  totalRegistrosHoy: number,
  totalRegistrosSesion: number,
  versionTerminal: string,
  conectadoDesde: string,
  escuela: string,
  ip: string,
  ramUsadaMB: number,
  espacioDiscoLibreGB: number,
  origen: "terminal_pi"
}
```

---

## Integración con Firebase

### Autenticación

Service Account con credenciales en `firebase-credentials.json` (chmod 600, en `.gitignore`).

```python
cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
```

### Escritura a producción

La terminal usa `.add()` para ID auto-generado (compatible con el web):

```python
_, doc_ref = db.collection("ingresos_cbtis").add(doc)
```

### Coordinación con sistema web

- **Sistema web** escribe a `ingresos_cbtis` con `modo: "facial"` o `"qr"` desde face-api.js/TOTP
- **Terminal Pi** escribe a `ingresos_cbtis` con `origen: "terminal_pi"` desde OpenCV/SFace
- **Panel admin** (v3.15.5) distingue ambos con badge "Terminal" cyan cuando `origen === "terminal_pi"`

### Rules Firestore

El service account (Admin SDK) bypasea reglas por diseño. No se requirieron cambios.

---

## Monitoreo remoto (heartbeat)

### Funcionamiento

La terminal escribe al documento `terminal_status/{terminalId}` cada 5 minutos (300s) durante operación normal.

Al iniciar: `estado = "online"` + heartbeat inmediato.  
Al detener (Ctrl+C o shutdown): `estado = "offline"`.  
Si crash abrupto: documento queda `"online"` con `ultimoHeartbeat` viejo → detectable como "stale" si >10min.

### Información reportada

- Temperatura CPU en tiempo real
- RAM utilizada
- Espacio disco libre
- Uptime del dispositivo
- IP local
- Total registros del día
- Total registros de la sesión
- Versión del software

### Panel admin "Terminales" (v3.15.5)

El sistema web tiene una sección dedicada:

- **Ruta:** Sidebar → Sistema → Terminales
- **Badge:** "Pi" en cyan junto al menú item
- **Roles autorizados:** admin, superadmin
- **Visualización:** lista de terminales con badge de estado (verde/rojo/amarillo), métricas en vivo, auto-refresh

---

## Arranque automático (systemd)

### Service file (`/etc/systemd/system/keyon-terminal.service`)

```ini
[Unit]
Description=KEYON Terminal Pro v2 - Face Recognition Kiosk
Documentation=https://github.com/santirivera-oss/keyon-terminal
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=keyon
Group=keyon
WorkingDirectory=/home/keyon/keyon-terminal
ExecStart=/usr/bin/python3 /home/keyon/keyon-terminal/scripts/terminal_main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=keyon-terminal
ExecStartPre=/bin/sleep 15
MemoryMax=400M
CPUQuota=90%

[Install]
WantedBy=multi-user.target
```

### Características

- **After=network-online.target** — espera WiFi antes de arrancar
- **ExecStartPre sleep 15** — da tiempo a cámara USB para inicializar
- **Restart=on-failure** — si Python crashea, reinicia automático
- **RestartSec=10** — espera 10s entre intentos de restart
- **MemoryMax=400M** — protección contra memory leaks
- **CPUQuota=90%** — deja 10% al sistema

### Comandos útiles

```bash
# Ver estado
sudo systemctl status keyon-terminal.service

# Ver logs en vivo
sudo journalctl -u keyon-terminal.service -f

# Reiniciar servicio
sudo systemctl restart keyon-terminal.service

# Detener (no deshabilita auto-start)
sudo systemctl stop keyon-terminal.service

# Deshabilitar auto-start al boot
sudo systemctl disable keyon-terminal.service

# Habilitar auto-start al boot
sudo systemctl enable keyon-terminal.service
```

### Validación post-reboot

**Test del 19 abril 23:40 CST:**

```
23:40:24  systemd.start (reboot completado)
23:40:40  service.Started
23:40:59  Python arranca (tras sleep 15s)
23:41:01  Modelos YuNet + SFace cargados
23:41:02  Firebase conectado
23:41:03  Heartbeat inicial enviado
23:41:13  PRIMER REGISTRO tras reboot sin intervención

Tiempo total boot → operativa: 49 segundos
```

---

## Scripts disponibles

### Flujo del kiosco

- **`terminal_main.py`** — Loop principal del kiosco (v2.0.3-dev)
  - Flags: `--dry-run` (sin Firebase), `--debug` (verboso)
  - Se ejecuta vía systemd en producción

### Enroll / registro

- **`db_init.py`** — Inicializa schema de BD
- **`registrar.py`** — Registra alumno con foto

### Identificación

- **`identificar.py`** — Identificación 1:N contra BD local
- **`reconocer_sface.py`** — Comparación 1:1 entre dos rostros

### Detección (testing)

- **`detectar_yunet.py`** — Prueba detección moderna
- **`deteccion_test.py`** — Prueba Haar Cascade (legacy)

### Firebase

- **`firebase_test.py`** — Test lectura Firestore
- **`firebase_write.py`** — Test escritura (legacy, usar terminal_main.py)
- **`firebase_cleanup_terminal.py`** — Limpia registros de prueba con `--delete`

---

## Guía de uso

### Setup inicial en una Pi nueva

```bash
# 1. Flashear Raspberry Pi OS Lite 64-bit con SSH + WiFi pre-configurado

# 2. Actualizar
sudo apt update && sudo apt upgrade -y

# 3. Activar SPI e I2C
sudo raspi-config  # Interface Options → SPI/I2C → Enable

# 4. Instalar dependencias
sudo apt install -y git python3-pip ffmpeg v4l-utils sqlite3
pip3 install opencv-python-headless numpy firebase-admin --break-system-packages

# 5. Clonar proyecto
git clone https://github.com/santirivera-oss/keyon-terminal.git ~/keyon-terminal
cd ~/keyon-terminal

# 6. Credenciales Firebase (copiar manualmente a ~/keyon-terminal/)
chmod 600 firebase-credentials.json

# 7. Inicializar BD
python3 scripts/db_init.py

# 8. Configurar systemd auto-start
sudo cp systemd/keyon-terminal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable keyon-terminal.service
sudo systemctl start keyon-terminal.service

# 9. Verificar
sudo systemctl status keyon-terminal.service
```

### Registro de alumnos

```bash
# Capturar foto
ffmpeg -f v4l2 -video_size 640x480 -i /dev/video0 -frames:v 1 -y /tmp/alumno.jpg

# Registrar
python3 scripts/registrar.py /tmp/alumno.jpg "Juan Pérez" "4BV" "AT0001"
```

### Apagar/Encender la Pi correctamente

```bash
# Apagar (shutdown limpio)
sudo poweroff

# Esperar a que LED verde se apague y quede solo el rojo
# Ya puedes desconectar cable de corriente

# Encender
# Reconectar cable. Arranque automático en ~90 segundos.
```

### Monitoreo

```bash
# Logs en tiempo real
sudo journalctl -u keyon-terminal.service -f

# Logs del archivo
tail -f ~/keyon-terminal/logs/kiosco.log

# Status del servicio
sudo systemctl status keyon-terminal.service

# Ver heartbeat en Firebase
# https://console.firebase.google.com/project/scanner-v3/firestore/data/~2Fterminal_status
```

---

## Métricas validadas

### Validación del 19 de abril de 2026

| Métrica | Valor | Umbral de referencia |
|---|---|---|
| Detección YuNet — confianza | 92-95% | mínimo 60% |
| Reconocimiento SFace — coseno | 0.722-0.834 | >0.363 (umbral match) |
| Reconocimiento SFace — L2 | 0.577-0.752 | <1.128 (umbral match) |
| Latencia captura ffmpeg (warm-up) | ~2-6 s | primera captura |
| Latencia captura (en operación) | 0.5-1 s | tras warm-up |
| Latencia inferencia + match | 2-3 s | n/a |
| Latencia end-to-end | ~3-5 s | aceptable para kiosco |
| Latencia escritura Firestore | ~500 ms | n/a |
| Boot a operativa (post-reboot) | 49 s | objetivo <2min |
| Temperatura CPU idle | 40-45 °C | throttling a 80 °C |
| Temperatura CPU en carga | 50-55 °C | margen amplio |
| RAM usada en operación | ~225 MB | de 416 disponibles |
| Voltaje del núcleo | 1.2563 V | nominal 1.2-1.3 V |
| Espacio disco libre | 105 GB | de 114 totales |

### Scores históricos récord

- **Máximo coseno de sesión:** 0.834 (19 abril, 21:11:33)
- **Mínimo L2 de sesión:** 0.577
- **Promedio coseno:** ~0.76
- **Promedio L2:** ~0.68

### Comparativa con sistema web v1

| Métrica | Sistema web v1 (face-api.js) | Terminal v2 (SFace nativo) |
|---|---|---|
| Precisión | 98.5% | ~99% (benchmark LFW) |
| Latencia | 1.2 s | ~3-5 s |
| Costo hardware | ~$4,900 | ~$3,225 |
| Consumo | ~50-100 W (PC) | ~2-5 W (Pi Zero 2W) |
| Autonomía | Requiere navegador + PC | 100% autónoma |
| Boot time | ~120s (OS + browser) | ~90s (OS + systemd service) |

---

## Bitácora de desarrollo

### Sesión única del 19 de abril de 2026

**Duración total:** 8 horas (19:00 – 00:00)  
**Horas productivas netas:** ~6.5 horas (descontando cena y baño)

#### Fase 1 — Setup base (19:00-23:30)

| Hora | Hito |
|---|---|
| 19:00 | microSD ADATA 128GB recibida, Raspberry Pi Imager descargado |
| 19:45 | Raspberry Pi OS Lite 64-bit flasheado + primer boot exitoso |
| 20:15 | SSH funcionando vía WiFi |
| 20:45 | Interfaces SPI e I2C activadas (edición manual de `/boot/firmware/config.txt`) |
| 21:00 | ffmpeg + v4l-utils + Logitech C270 detectada en `/dev/video0` |
| 21:15 | Primera captura 640x480 YUYV @ 30 fps |
| 21:30 | OpenCV 4.13 + NumPy 2.4 instalados vía pip3 |
| 21:45 | Primera detección facial con Haar Cascade |
| 22:00 | Modelos YuNet + SFace descargados del OpenCV Model Zoo |
| 22:15 | YuNet detectando rostros con 94% confianza |
| 22:30 | SFace comparación 1:1 exitosa (cos=0.7260) |
| 22:45 | SQLite inicializada con tablas alumnos y asistencias |
| 23:00 | Primer alumno registrado (Santiago Rivera, 4BV, AT2099) |
| 23:15 | `identificar.py` funcional — primera identificación 1:N exitosa |
| 23:25 | firebase-admin 7.4.0 instalado, service account configurado |
| 23:30 | Primera escritura a Firestore (colección `asistencias_terminal`) |

#### Pausa cena + baño (23:30-20:45 del día siguiente)

#### Fase 2 — Integración con sistema web (20:45-21:22)

| Hora | Hito |
|---|---|
| 20:45 | Schema definitivo acordado con Claude Code |
| 20:55 | v1.2.1 con schema compatible `ingresos_cbtis` |
| 21:11 | **PRIMER REGISTRO EN PRODUCCIÓN** — doc id `Cc5sleYZoGK3J8w39xBo` |
| 21:22 | Badge "Terminal" validado en panel admin web v3.15.4 |

#### Pausa cena + baño (21:22-22:41)

#### Fase 3 — GitHub + production hardening (22:45-00:00)

| Hora | Hito |
|---|---|
| 22:45 | Git config con identidad Santiago Rivera |
| 23:00 | 3 commits atómicos + push inicial a GitHub |
| 23:10 | Tag v2.0.1-dev — primer release funcional |
| 23:17 | v2.0.2-dev — logs a archivo con rotación + errores robustos |
| 23:29 | v2.0.3-dev — heartbeat a `terminal_status` funcionando |
| 23:36 | systemd service file creado y validado |
| 23:40 | **AUTO-START POST-REBOOT VALIDADO** — 49s boot → operativa |
| 23:45 | v2.0.4-dev con systemd versionado en GitHub |
| ~00:00 | Claude Code deploya v3.15.5 con panel "Terminales" |

#### Releases publicados en GitHub

| Tag | Descripción | Features |
|---|---|---|
| v2.0.1-dev | First functional release | Pipeline básico + Firebase |
| v2.0.2-dev | File logging + resilience | Logs rotativos, error handling |
| v2.0.3-dev | Heartbeat monitoring | terminal_status cada 5min |
| v2.0.4-dev | Systemd auto-start | Service file + reboot-validated |

#### Problemas técnicos resueltos durante el día

1. **WiFi mal configurado en Imager** — SSID typo, resuelto re-flasheando
2. **SSH host key changed** — tras re-flasheo, resuelto con `ssh-keygen -R`
3. **SPI/I2C no activadas** por raspi-config — editado manualmente `config.txt`
4. **Módulo i2c-dev no cargaba** — agregado a `/etc/modules-load.d/`
5. **apt install falla con libxnvctrl0** — bypass usando pip3 con `opencv-python-headless`
6. **Bracketed paste en bash** — escribiendo manualmente
7. **Nano cortando primera línea** — verificación con `head` tras pegados
8. **Timeout ffmpeg con frame 10** — bajado a frame 5 + timeout 10s
9. **Schema incorrecto inicial** — Claude Code detectó que web usa `ingresos_cbtis` no `asistencias`
10. **Repo GitHub con guión inicial** — renombrado desde Settings
11. **firebase_cleanup.pynano** — archivo basura por typo de nano, eliminado pre-commit
12. **logs/ no en .gitignore** — agregado antes de primer commit de v2.0.3

---

## Consideraciones de seguridad y LFPDPPP

### Artículos cubiertos (heredados del sistema web)

- **Art. 8** — Consentimiento informado previo
- **Art. 9** — Datos personales sensibles (biométricos) con medidas reforzadas
- **Art. 16** — Aviso integral de privacidad (10 secciones completas)
- **Art. 17** — Finalidades primarias y ausencia de secundarias
- **Art. 19** — Deber de seguridad
- **Art. 22** — Derechos ARCO
- **Art. 23** — Trazabilidad y logs inmutables

### Medidas técnicas Terminal Pro v2

- **BD local:** Permisos `chmod 600` en `keyon.db` (solo usuario `keyon`)
- **Credenciales:** Permisos `chmod 600` en `firebase-credentials.json`
- **Exclusión de Git:** `.gitignore` protege todo dato sensible
- **HTTPS/TLS:** Conexión a Firebase vía TLS 1.2+ (Google enforced)
- **Service account restrictivo:** Solo escribe a `ingresos_cbtis` y `terminal_status`
- **Logs persistentes:** Rotación diaria con 30 días de retención (auditoría)
- **Systemd sandboxing:** Límites de memoria (400MB) y CPU (90%)

### Pendientes para Bloque B (post-nacional)

- Implementar descifrado AES-GCM-256 en Python para leer `biometricos_seguros`
- Aviso de privacidad en pantalla del kiosco al momento de captura
- Portal ARCO auto-servicio para padres/tutores
- Pen-test de derivación de clave por schoolId

### Algoritmo de cifrado (Bloque B)

Documentado en detalle en `tools/TERMINAL-PRO-INTEGRATION.md` del repo web:

```
AES-GCM-256
PBKDF2-HMAC-SHA256 con 150,000 iteraciones
Salt de 32 bytes random (único por escuela en _config/biometric_salt)
Seed: "SCHOOL_KEY_CBTIS001_KEYON_BIOMETRIC_2026"
IV: 12 bytes random por encriptación
Gotcha: salt se pasa a PBKDF2 como UTF-8 del string base64, NO bytes decodificados
```

---

## Limitaciones conocidas

1. **Pantalla SPI aún no conectada** — pendiente soldar headers (lunes 20 abril)
2. **Audio no conectado** — PAM8403 + bocinas esperan headers
3. **No integrado con ESP32 v8.3 PIR** — falta WebSocket bridge
4. **BD local NO sincroniza con web** — Bloque B pendiente
5. **Comparación secuencial O(n)** — para >500 alumnos requeriría FAISS
6. **Single-band WiFi** — no compatible con routers 5GHz only
7. **Sensibilidad a iluminación** — faltan pruebas con luz natural extrema

---

## Roadmap

### Inmediato (semana del 20-26 abril 2026)

- [ ] Comprar headers 40 pines en Steren Fresnillo (lunes)
- [ ] Soldar headers con supervisión en CBTis (lunes-martes)
- [ ] Conectar pantalla SPI ILI9486 con drivers fbtft/fbcp
- [ ] Conectar PAM8403 + bocinas
- [ ] Actualizar documentos CNPyPE para upload del miércoles 22
- [ ] Integrar ESP32 v8.3 PIR vía WebSocket bridge
- [ ] Grabar video demo de 3-5 min
- [ ] Imprimir case 3D con branding Exara

### CNPyPE Nacional (semana del 27 abril)

- [ ] Montaje final del kiosco
- [ ] Pruebas finales de estabilidad
- [ ] Transporte al lugar del nacional
- [ ] Defensa del proyecto

### Post-nacional (mayo 2026)

- [ ] Implementar descifrado AES-GCM-256 en Python (Bloque B)
- [ ] Aviso de privacidad en pantalla del kiosco
- [ ] Portal ARCO auto-servicio
- [ ] Optimización con FAISS para N > 500
- [ ] Soporte multilingüe (español + inglés + náhuatl)
- [ ] Modo offline con buffer y sync diferido

### Largo plazo

- [ ] Adaptación a Raspberry Pi 5 (más potencia, AI accelerator)
- [ ] Certificación de privacidad por tercero
- [ ] Paquete Debian `.deb` con un comando
- [ ] Sistema OTA para updates remotos
- [ ] Dashboard de analytics operativos agregados

---

## Autor y licencia

**Santiago Rivera López**  
Fundador y desarrollador principal — **Exara Studio**  
Alumno — CBTis No. 001, Fresnillo, Zacatecas, México

- Sitio web: [exara.uk](https://exara.uk)
- Correo: contacto@exara.uk
- Teléfono: +52 493 188 7739
- GitHub: [@santirivera-oss](https://github.com/santirivera-oss)

### Asesoría académica

- **Mtra. María Magdalena Escarcia Lozano** — Asesora técnica (hardware, electrónica)
- **Mtra. Lorena Santana Martínez** — Asesora metodológica (investigación, documentación)
- **Mtra. Daniela Morillo** — Departamento de Vinculación con el Sector Productivo, CBTis 001

### Colaboradores de desarrollo

- **Sistema web v3.x** — co-desarrollado con Claude Code (Anthropic)
- **Terminal Pro v2** — co-desarrollado con Claude (Anthropic)
- **Integración paralela** — coordinación entre ambas instancias

### Licencia

Copyright © 2026 Santiago Rivera López / Exara Studio

Todos los derechos reservados. Este software y su documentación son propiedad intelectual de Santiago Rivera López / Exara Studio y están protegidos bajo los derechos de autor aplicables en los Estados Unidos Mexicanos.

Para uso académico, educativo o investigativo no-comercial contactar a contacto@exara.uk para autorización específica.

---

## Agradecimientos

- **OpenCV** — por el Model Zoo con YuNet y SFace de libre uso
- **Google Firebase** — por la infraestructura Firestore y Hosting
- **Raspberry Pi Foundation** — por hardware accesible y documentación abierta
- **Anthropic** — por Claude y Claude Code (trabajo en paralelo coordinado)
- **Comunidad open-source** — por las herramientas que hacen esto posible

---

## Versiones

| Versión | Fecha | Features principales |
|---|---|---|
| v2.0.1-dev | 19 abril 2026, 23:10 | First functional release, pipeline Firebase |
| v2.0.2-dev | 19 abril 2026, 23:17 | File logging + error resilience |
| v2.0.3-dev | 19 abril 2026, 23:29 | Heartbeat to terminal_status |
| v2.0.4-dev | 19 abril 2026, 23:45 | Systemd auto-start (reboot validated) |

### Releases del ecosistema web coordinados

| Versión web | Fecha | Terminal-related changes |
|---|---|---|
| v3.15.4 | 19 abril 2026 | Badge "Terminal" en admin-dashboard + alumno-main |
| v3.15.5 | 20 abril 2026, ~00:00 | Panel "Terminales" + rules Firestore |

---

*Documento actualizado el 20 de abril de 2026 a las 00:00 CST como parte del proceso de desarrollo de Keyon Terminal Pro v2, proyecto presentado al XXVIII Concurso Nacional de Prototipos y Proyectos de Emprendimiento (CNPyPE) 2026 — Fase Nacional, registro 26-AT2099.*

---

**🏆 Hito destacado:** En una sola jornada del 19 de abril de 2026, este proyecto pasó de ser una microSD vacía a un sistema embebido de reconocimiento facial con auto-start validado post-reboot, monitoreo remoto vía Firestore, y integración con sistema web en producción. Todo sobre hardware de ~$3,225 MXN.
