# KEYON Terminal Pro v2

Sistema de reconocimiento facial nativo para control de asistencia escolar, desplegado sobre hardware embebido Raspberry Pi Zero 2W, con integración directa al ecosistema Firebase del proyecto Keyon Access System.

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
- Arquitectura lista para integrarse con el módulo ESP32 v8.3 PIR legado (pantalla TFT + sensores PIR + VL53L0X + buzzer)

El sistema fue validado funcionalmente el 19 de abril de 2026 con registro end-to-end completo: captura de frame → detección YuNet → alineación facial → embedding 128-dim SFace → búsqueda en BD local → escritura de registro en Firebase Firestore con timestamp de servidor Google.

---

## Contexto del proyecto

### Proyecto matriz: Keyon Access System

Keyon es un sistema integral de control de asistencia escolar con biometría facial y códigos QR dinámicos TOTP, en **operación en producción** en el CBTis No. 001 de Fresnillo, Zacatecas. El sistema completo incluye:

- **Web PWA** (React + TypeScript + Firebase) — panel administrativo, pase de lista para profesores, interfaces para alumnos
- **App móvil React Native Expo** — para padres de familia con notificaciones push
- **Cloud Functions** desplegadas en `us-central1` — notificaciones y lógica serverless
- **Módulo ESP32 v8.3 PIR** — sensores PIR + VL53L0X + buzzer + pantalla TFT ILI9341 con comunicación WebSocket
- **Cumplimiento LFPDPPP completo (Bloque A)** — cifrado AES-GCM-256 + PBKDF2 150,000 iteraciones, aviso integral de privacidad, derechos ARCO

### Registro oficial

- **Número de registro CNPyPE 2026:** 26-AT2099
- **Categoría:** Alumno-Tecnológico
- **Plantel:** CBTis No. 001, Fresnillo, Zacatecas
- **Fase:** Nacional (1er lugar estatal CNPyPE 2026)
- **Repositorio web:** [github.com/santirivera-oss/SCANER-V3](https://github.com/santirivera-oss/SCANER-V3)

### Motivación de Terminal Pro v2

La versión web original requiere una PC con navegador en cada kiosco, lo cual implica:
- Mayor costo de hardware (~$4,900 MXN por kiosco PC + periféricos)
- Mayor consumo energético
- Requiere administración de sistema operativo completo
- Dependencia de Chromium con face-api.js limitado a ~1.2 segundos por reconocimiento

Terminal Pro v2 reduce el costo a ~$2,670 MXN por unidad, opera en 5V 3A, ejecuta Debian Lite sin escritorio gráfico, y usa modelos ONNX cuantizados para inferencia directa sobre CPU ARM, eliminando la capa de navegador y JavaScript.

---

## Arquitectura del sistema

```
┌──────────────────────────────────────────────────────────────┐
│                    ECOSISTEMA KEYON                          │
│                                                              │
│  ┌─────────────────┐              ┌──────────────────────┐   │
│  │  Sistema Web    │              │  Terminal Pro v2     │   │
│  │  v3.12.0        │              │  (este proyecto)     │   │
│  │                 │              │                      │   │
│  │  React+TS+PWA   │              │  Python+OpenCV       │   │
│  │  Firebase Hosting│              │  YuNet + SFace       │   │
│  │  Chromium       │              │  SQLite local        │   │
│  │  face-api.js    │              │  ARM Cortex-A53      │   │
│  └────────┬────────┘              └───────────┬──────────┘   │
│           │                                    │              │
│           └──────────────┬─────────────────────┘              │
│                          │                                    │
│                          ▼                                    │
│           ┌──────────────────────────┐                        │
│           │  Firebase Firestore      │                        │
│           │  (scanner-v3)            │                        │
│           │                          │                        │
│           │  43 colecciones:         │                        │
│           │  - alumnos               │                        │
│           │  - asistencias           │                        │
│           │  - asistencias_terminal  │  ← colección nueva    │
│           │  - biometricos_seguros   │    para Terminal v2   │
│           │  - consentimientos       │                        │
│           │  - ... (40 más)          │                        │
│           └──────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

### Flujo de datos en Terminal Pro v2

```
[1] Cámara Logitech C270 captura frame 640x480 YUY2 @ 30 fps
                    │
                    ▼
[2] YuNet ONNX detecta rostros con bounding boxes + 5 landmarks
                    │
                    ▼
[3] SFace.alignCrop alinea el rostro usando los landmarks
                    │
                    ▼
[4] SFace.feature genera embedding 128-dim (float32, 512 bytes)
                    │
                    ▼
[5] SQLite query recupera todos los embeddings registrados
                    │
                    ▼
[6] Comparación coseno + L2 vs cada embedding registrado
                    │
                    ▼
[7] Selección del match más confiable superando umbrales
                    │
                    ▼
[8] Registro de asistencia en SQLite local (fallback offline)
                    │
                    ▼
[9] Sincronización inmediata con Firestore asistencias_terminal
```

---

## Hardware

### Placa principal

- **Modelo:** Raspberry Pi Zero 2W Rev 1.0
- **Procesador:** Broadcom BCM2710A1, núcleo ARM Cortex-A53 quad-core @ 1 GHz (ARMv8, 64-bit)
- **RAM:** 512MB LPDDR2 SDRAM (416 MB efectivos disponibles tras reserva GPU)
- **Memoria swap:** 415 MB auxiliar en microSD
- **Almacenamiento:** microSD ADATA Premier 128GB UHS-I V10 A1 (114 GB útiles tras formateo)
- **Conectividad:** WiFi 802.11 b/g/n 2.4 GHz + Bluetooth 4.2/BLE
- **Interfaces activas:** SPI (`/dev/spidev0.0`, `/dev/spidev0.1`), I2C (`/dev/i2c-1`, `/dev/i2c-2`)
- **Temperatura en idle:** 47.2 °C (dentro del rango óptimo, umbral throttling a 80 °C)
- **Voltaje del núcleo:** 1.2563 V (nominal y estable)

### Periféricos

- **Cámara:** Logitech C270 HD Webcam (VID 046d, PID 0825) vía cable OTG Soku V8 Micro USB → USB 3.0
  - Resolución usada: 640x480 YUYV @ 30 fps
  - Resoluciones soportadas: hasta 1280x720 @ 15 fps
- **Pantalla (opcional):** 3.5" SPI ILI9486 480x320 táctil
- **Audio:** 2x módulos amplificadores PAM8403 2x3W + 2x bocinas 50mm 4Ω 3W metálicas
- **Fuente de poder:** Tecneu 5V 3A con botón ON/OFF

### Presupuesto de hardware

| Componente | Costo (MXN) |
|---|---|
| Raspberry Pi Zero 2W | 806.44 |
| Fuente 5V 3A Tecneu | 139.56 |
| microSD ADATA 128GB | 378.00 |
| Cámara Logitech C270 | 486.00 |
| Pantalla SPI 3.5" ILI9486 | 474.05 |
| Cable OTG Soku V8 | 159.99 |
| 2x PAM8403 | 84.36 |
| 2x Bocinas 50mm 4Ω | 141.55 |
| **Total hardware** | **2,669.95** |
| Headers 40 pines (pendiente) | ~35.00 |
| Adaptador mini-HDMI (pendiente) | ~120.00 |
| Cautín/estaño (prestado CBTis) | 0.00 |
| Case 3D impreso (pendiente) | ~400.00 |
| **Total proyectado** | **~3,225.00** |

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
- **Shell:** bash 5.x
- **Gestor de servicios:** systemd

### Runtime y librerías Python

- **Python 3.13.5** (pre-instalado en Raspberry Pi OS Lite)
- **pip3** 25.1.1
- **numpy** 2.4.4 (cálculo vectorial)
- **opencv-python-headless** 4.13.0.92 (visión por computadora sin GUI)
- **firebase-admin** 7.4.0 (SDK oficial Firebase)
- **google-cloud-firestore** 2.27.0 (cliente Firestore)
- **sqlite3** (biblioteca estándar Python + CLI 3.46.1)

### Modelos de inteligencia artificial

- **Detección:** YuNet `face_detection_yunet_2023mar.onnx`
  - Fuente: [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo) (oficial)
  - Arquitectura: MobileNetV2 cuantizada
  - Tamaño: 228 KB
  - Entrada: RGB 640x480 (redimensionable)
  - Salida: bounding boxes + 5 landmarks faciales + score de confianza

- **Reconocimiento:** SFace `face_recognition_sface_2021dec.onnx`
  - Fuente: [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo) (oficial)
  - Arquitectura: ResNet-50 optimizada
  - Tamaño: 37 MB
  - Entrada: rostro alineado 112x112 RGB
  - Salida: embedding 128-dim float32 (512 bytes)

### Herramientas de desarrollo

- **Git** 2.47.3 — control de versiones
- **tmux** 3.5a — sesiones persistentes (planeado)
- **nano** — editor de texto
- **ffmpeg** 7.1.3 — captura de video/imagen desde cámara
- **v4l-utils** — diagnóstico de Video4Linux2
- **sqlite3** CLI — consulta directa a BD

### Configuración de interfaces

Configuración activada en `/boot/firmware/config.txt`:
```
dtparam=i2c_arm=on
dtparam=spi=on
dtparam=audio=on
```

Módulo `i2c-dev` cargado automáticamente vía `/etc/modules-load.d/i2c.conf`.

---

## Estructura del repositorio

```
/home/keyon/keyon-terminal/
├── README.md                           Este archivo
├── .gitignore                          Exclusiones de Git
├── firebase-credentials.json           🔑 Service account (NO subir a Git)
│
├── db/
│   └── keyon.db                        Base de datos SQLite local
│
├── modelos/
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
│
├── docs/                               Documentación adicional (TBD)
│
└── scripts/
    ├── db_init.py                      Inicializar schema de BD
    ├── deteccion_test.py               Prueba detección con Haar Cascade
    ├── detectar_yunet.py               Detección moderna con YuNet
    ├── reconocer_sface.py              Comparación 1:1 entre dos rostros
    ├── registrar.py                    Registrar alumno en BD local
    ├── identificar.py                  Identificación 1:N contra BD
    ├── firebase_test.py                Prueba de conexión a Firestore
    └── firebase_write.py               Prueba de escritura a Firestore
```

---

## Pipeline de reconocimiento facial

### Etapa 1 — Captura de imagen

Usamos ffmpeg vía el driver UVC (USB Video Class) nativo de Linux:

```bash
ffmpeg -f v4l2 -video_size 640x480 -i /dev/video0 \
       -vf "select='eq(n,10)'" \
       -frames:v 1 -update 1 /tmp/captura.jpg
```

El filtro `select='eq(n,10)'` captura el frame 10 para dar tiempo al sensor de auto-calibrar exposición y balance de blancos (los primeros 5-8 frames en C270 salen subexpuestos).

### Etapa 2 — Detección con YuNet

```python
detector = cv2.FaceDetectorYN.create(
    "face_detection_yunet_2023mar.onnx",
    "",
    (640, 480),
    score_threshold=0.6,    # 60% confianza mínima
    nms_threshold=0.3,      # Non-Maximum Suppression
    top_k=5000              # máximo rostros candidatos
)

_, rostros = detector.detect(imagen)
```

Cada rostro detectado incluye:
- Bounding box (x, y, width, height)
- 5 landmarks: ojo izquierdo, ojo derecho, punta de la nariz, comisura izquierda de boca, comisura derecha de boca
- Score de confianza (0.0 a 1.0)

### Etapa 3 — Alineación facial

```python
rostro_alineado = reconocedor.alignCrop(imagen, rostro)
```

SFace usa los 5 landmarks para rotar y escalar el rostro a un formato canónico 112x112 RGB, asegurando que los ojos queden horizontales y centrados. Esto normaliza la pose antes del embedding.

### Etapa 4 — Generación de embedding

```python
embedding = reconocedor.feature(rostro_alineado)
# embedding.shape == (1, 128), dtype float32, 512 bytes
```

El embedding es un vector 128-dimensional que representa las características únicas del rostro en un espacio latente. Dos fotos de la misma persona producen vectores cercanos; dos personas distintas producen vectores alejados.

### Etapa 5 — Comparación

Dos métricas complementarias:

**Distancia coseno** (más alta = más similar):
```
cos(A, B) = (A · B) / (||A|| × ||B||)
```
- Rango: -1 a 1 (en la práctica 0 a 1 por normalización de SFace)
- Umbral match (OpenCV oficial): `> 0.363`

**Distancia L2** (más baja = más similar):
```
L2(A, B) = ||A - B||_2
```
- Rango: 0 a ~2 (vectores L2-normalizados)
- Umbral match (OpenCV oficial): `< 1.128`

Se considera match válido cuando **ambas** métricas superan sus umbrales simultáneamente. Esta doble validación reduce falsos positivos.

---

## Modelo de datos

### SQLite local (`db/keyon.db`)

**Tabla `alumnos`** — perfiles biométricos registrados en la terminal:

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

CREATE INDEX idx_alumnos_matricula ON alumnos(matricula);
```

**Tabla `asistencias`** — log local para operación offline:

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

CREATE INDEX idx_asistencias_timestamp ON asistencias(timestamp);
CREATE INDEX idx_asistencias_sync ON asistencias(sincronizado_firebase);
```

### Firestore (`scanner-v3`)

**Colección nueva `asistencias_terminal`** — creada por Terminal Pro v2 sin afectar las colecciones del sistema web:

```typescript
{
  alumnoId: string,              // ej: "AT2099"
  nombre: string,                // nombre completo
  grupo: string,                 // ej: "4BV"
  tipo: "entrada" | "salida",
  timestamp: Timestamp,          // hora del servidor Google
  timestampLocal: string,        // ISO 8601 local
  metodoVerificacion: "facial_local_terminal",
  scoreCosine: number,
  scoreL2: number,
  terminalId: string,            // ej: "keyon-pi-zero2w-01"
  dispositivo: string,           // ej: "Raspberry Pi Zero 2W"
  procesadoEnDispositivo: boolean,
  sincronizadoFirebase: boolean,
  version: string                // ej: "2.0.0-dev"
}
```

Esta colección separada permite al panel administrativo web distinguir entre registros generados por el sistema web (face-api.js en browser) y registros del kiosco físico (SFace nativo en Pi), manteniendo trazabilidad completa.

---

## Integración con Firebase

### Autenticación

La Terminal Pro v2 usa un **service account** con credenciales descargadas de Firebase Console (Project Settings → Service accounts → Generate new private key). El archivo JSON resultante se coloca en `/home/keyon/keyon-terminal/firebase-credentials.json` con permisos `600` (solo lectura para el owner).

### Cliente Firestore

```python
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
```

### Proyecto Firebase

- **Project ID:** `scanner-v3`
- **Región:** `us-central1`
- **43 colecciones totales**
- **10 alumnos registrados** (al momento de validación)

### Colecciones detectadas

```
_admin_logs, _config, _security_logs, _system,
admin_logs, admin_profiles, alumnos, asignaciones,
asistencias, asistencias_terminal (nueva), avisos,
biometric_access_logs, biometricos_seguros, calificaciones,
chats, chats_padres, citatorios, clases_profesor,
consent_codes, consent_logs, consent_pending, consentimientos,
datos_biometricos, directivos, entregas, faltas_por_retardos,
historial, horarios, ingresos_cbtis, justificantes,
logs_facial, notificaciones, notificaciones_enviadas,
padres_codigos, padres_tokens, pases_salida, profesores,
registros, reportes, reportes_disciplina, security_logs,
sesiones, tareas, usuarios
```

---

## Scripts disponibles

### `db_init.py`

Inicializa el schema de la base de datos SQLite. Crea las tablas `alumnos` y `asistencias` con sus índices correspondientes.

```bash
python3 scripts/db_init.py
```

Si la BD ya existe, pregunta confirmación antes de borrarla.

### `registrar.py`

Registra un nuevo alumno en la BD local extrayendo su embedding facial desde una foto.

```bash
python3 scripts/registrar.py <ruta_foto> <nombre> <grupo> [matricula]
```

Ejemplo:
```bash
python3 scripts/registrar.py /tmp/foto1.jpg "Santiago Rivera" "4BV" "AT2099"
```

Alerta si la confianza de detección es menor al 85% y pide confirmación.

### `identificar.py`

Identifica a un alumno 1:N contra toda la BD local y retorna el match más confiable.

```bash
python3 scripts/identificar.py <ruta_foto>
```

Salida esperada:
```
IDENTIFICADO: Santiago Rivera
Grupo: 4BV | Matricula: AT2099
Scores: cos=0.7260 | L2=0.7403
```

### `detectar_yunet.py`

Prueba de detección facial con YuNet. Muestra coordenadas, confianza y landmarks de cada rostro.

### `reconocer_sface.py`

Compara 1:1 entre dos fotos y dicta si son la misma persona.

```bash
python3 scripts/reconocer_sface.py /tmp/foto1.jpg /tmp/foto2.jpg
```

### `firebase_test.py`

Verifica conectividad con Firebase, lista todas las colecciones del proyecto y muestra una muestra de 5 alumnos del Firestore.

### `firebase_write.py`

Escribe un documento de prueba en la colección `asistencias_terminal` y lo relee para validar la escritura.

### `deteccion_test.py`

Detección legacy con Haar Cascade (solo como referencia histórica de lo primero que funcionó). YuNet lo supera en precisión.

---

## Guía de uso

### Primer setup en una Pi nueva

1. **Flashear Raspberry Pi OS Lite 64-bit** usando Raspberry Pi Imager con personalización:
   - Hostname, usuario, password configurados
   - SSH activado con autenticación por contraseña
   - WiFi pre-configurado

2. **Actualizar sistema:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Activar SPI e I2C** vía `sudo raspi-config` → Interface Options → SPI/I2C → Enable.

4. **Instalar dependencias:**
   ```bash
   sudo apt install -y git python3-pip ffmpeg v4l-utils sqlite3
   pip3 install opencv-python-headless numpy firebase-admin --break-system-packages
   ```

5. **Clonar el proyecto:**
   ```bash
   git clone https://github.com/santirivera-oss/keyon-terminal.git ~/keyon-terminal
   cd ~/keyon-terminal
   ```

6. **Descargar modelos ONNX:**
   ```bash
   cd modelos
   wget https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
   wget https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
   ```

7. **Configurar credenciales Firebase:**
   - Descargar service account JSON de Firebase Console
   - Copiarlo a `~/keyon-terminal/firebase-credentials.json`
   - `chmod 600 firebase-credentials.json`

8. **Inicializar BD:**
   ```bash
   python3 scripts/db_init.py
   ```

### Flujo típico de uso

```bash
# Registrar alumno
python3 scripts/registrar.py /tmp/alumno1.jpg "Juan Pérez" "4BV" "AT0001"

# Identificar alumno (captura nueva foto primero)
ffmpeg -f v4l2 -video_size 640x480 -i /dev/video0 -frames:v 1 -update 1 -y /tmp/nueva.jpg
python3 scripts/identificar.py /tmp/nueva.jpg
```

---

## Métricas validadas

### Validación 19 abril 2026

| Métrica | Valor | Umbral de referencia |
|---|---|---|
| Detección YuNet — confianza | 92-95% | mínimo 60% |
| Reconocimiento SFace — coseno | 0.7260 | mínimo 0.363 |
| Reconocimiento SFace — L2 | 0.7403 | máximo 1.128 |
| Latencia captura ffmpeg | ~2.1 s | n/a |
| Latencia inferencia YuNet + SFace | <1 s | n/a |
| Latencia escritura Firestore | ~500 ms | n/a |
| **Latencia end-to-end** | **~3 s** | comparable a face-api.js web |
| Temperatura CPU en idle | 47.2 °C | throttling a 80 °C |
| RAM usada durante inferencia | ~200 MB | 416 MB disponibles |
| Voltaje del núcleo | 1.2563 V | nominal 1.2-1.3 V |

### Comparativa con sistema web v1

| Métrica | Sistema web v1 (face-api.js) | Terminal v2 (SFace nativo) |
|---|---|---|
| Precisión | 98.5% | ~99% (benchmark LFW) |
| Latencia | 1.2 s | ~3 s |
| Costo hardware | ~$4,900 | ~$3,225 |
| Consumo | ~50-100 W (PC) | ~2-5 W (Pi Zero 2W) |
| Independencia | requiere navegador | autónoma |

Nota: la mayor latencia de Terminal v2 (3s vs 1.2s) se compensa con menor costo, menor consumo y autonomía operativa. Es aceptable para el caso de uso (kiosco de entrada, no tiempo real extremo).

---

## Bitácora de desarrollo

### Sesión del 19 de abril de 2026

**Duración:** 4 horas y 30 minutos (19:00 – 23:30)

**Objetivo:** Configurar la Raspberry Pi Zero 2W y validar el pipeline completo de reconocimiento facial + integración Firebase.

#### Hitos cronológicos

| Hora | Hito |
|---|---|
| 19:00 | microSD ADATA 128GB recibida, Raspberry Pi Imager descargado |
| 19:45 | Raspberry Pi OS Lite 64-bit flasheado + primer boot exitoso |
| 20:15 | SSH funcionando vía WiFi (tras resolver problema de SSID del router FiberStore + typo en credencial + conflicto de known_hosts tras re-flasheo) |
| 20:30 | Sistema actualizado con `apt update && apt upgrade` |
| 20:45 | Interfaces SPI e I2C activadas (requirió edición manual de `/boot/firmware/config.txt` y módulo `i2c-dev` en `/etc/modules-load.d/`) |
| 21:00 | ffmpeg + v4l-utils instalados, cámara Logitech C270 identificada en `/dev/video0` |
| 21:15 | Primera captura de video 640x480 YUYV @ 30 fps exitosa |
| 21:30 | OpenCV 4.13 + NumPy 2.4 instalados vía pip3 (apt falló por problema con `libxnvctrl0` no aplicable a ARM) |
| 21:45 | Primera detección facial con Haar Cascade funcionando |
| 22:00 | Modelos YuNet + SFace descargados del OpenCV Model Zoo oficial |
| 22:15 | Detección con YuNet funcionando — 94% confianza en rostro principal |
| 22:30 | Comparación 1:1 SFace funcionando — cos=0.7260, L2=0.7403 (match válido) |
| 22:45 | Base de datos SQLite inicializada con tablas `alumnos` y `asistencias` |
| 23:00 | Primer alumno registrado (ID=1, "Santiago Rivera", "4BV", "AT2099") |
| 23:15 | Script `identificar.py` funcional — primera identificación 1:N exitosa |
| 23:25 | firebase-admin 7.4.0 instalado, service account configurado |
| 23:30 | **Primera escritura a Firestore exitosa** — documento en `asistencias_terminal` con timestamp de servidor Google visible en Firebase Console |

#### Problemas técnicos resueltos

1. **Router WiFi mal configurado** — el SSID tenía un carácter típico incorrecto en el Imager; resuelto re-flasheando.
2. **SSH host key changed** — tras re-flasheo, la Pi generó nuevas llaves y Windows bloqueó conexión; resuelto con `ssh-keygen -R`.
3. **Confusión de usuarios** — se crearon dos usuarios entre flasheos (`zero-exara` y `keyon`); clarificado con revisión de capturas del Imager.
4. **SPI/I2C no activadas automáticamente** — `raspi-config` no descomentó las líneas en `config.txt`; resuelto editando manualmente con nano.
5. **Módulo i2c-dev no cargaba** — requiere entrada explícita en `/etc/modules-load.d/` en Debian Trixie (sistema moderno); `/etc/modules` está obsoleto.
6. **apt install falla con libxnvctrl0** — dependencia de NVIDIA no aplicable a ARM; bypass usando pip3 con `opencv-python-headless`.
7. **Bracketed paste en bash** — códigos de escape `[200~` al pegar comandos; resuelto escribiendo manualmente.
8. **Nano cortando primera línea** — al pegar código largo a veces se pierde el primer `import`; solución verificar con `head` después de cada edición.

#### Archivos creados durante la sesión

- `scripts/deteccion_test.py` — primera prueba Haar
- `scripts/detectar_yunet.py` — detección moderna
- `scripts/reconocer_sface.py` — comparación 1:1
- `scripts/db_init.py` — schema SQLite
- `scripts/registrar.py` — registro de alumnos
- `scripts/identificar.py` — identificación 1:N
- `scripts/firebase_test.py` — test lectura Firebase
- `scripts/firebase_write.py` — test escritura Firebase

---

## Consideraciones de seguridad y LFPDPPP

Terminal Pro v2 hereda el modelo de cumplimiento del **Bloque A LFPDPPP** del sistema web principal:

### Artículos cubiertos

- **Art. 8** — Consentimiento informado previo
- **Art. 9** — Datos personales sensibles (biométricos) con medidas reforzadas
- **Art. 16** — Aviso integral de privacidad (10 secciones completas)
- **Art. 17** — Finalidades primarias y ausencia de secundarias
- **Art. 19** — Deber de seguridad
- **Art. 22** — Derechos ARCO (Acceso, Rectificación, Cancelación, Oposición)
- **Art. 23** — Trazabilidad y logs inmutables

### Medidas técnicas

- **Cifrado en reposo (sistema web):** AES-GCM-256 con PBKDF2 150,000 iteraciones SHA-256
- **Cifrado en tránsito:** TLS 1.2+ en todas las conexiones a Firebase (enforced por Google)
- **Permisos de archivos:** `chmod 600` en credenciales y BD local
- **Service account restrictivo:** solo puede escribir a `asistencias_terminal`, no accede a biométricos cifrados
- **Logs inmutables:** rules de Firestore impiden update/delete de entradas históricas
- **Retención:** 180 días post-baja académica (heredado del sistema web)

### Roadmap LFPDPPP para Terminal v2 (pendiente)

- Implementar descifrado AES-256 del `biometricos_seguros` del web para unificar BD (Bloque B)
- Agregar aviso de privacidad en pantalla del kiosco físico al momento de captura
- Implementar portal ARCO auto-servicio para padres/tutores
- Pen-test de la derivación de clave por `schoolId`

---

## Limitaciones conocidas

1. **Bucle de reconocimiento aún no implementado** — los scripts actuales son one-shot (una foto por ejecución). Se requiere un loop de captura continua para operación como kiosco real.

2. **Sin UI en la pantalla de la Pi** — la pantalla SPI ILI9486 adquirida aún no tiene drivers configurados. Se planea usar fbtft o fbcp-ili9341.

3. **Audio no conectado** — PAM8403 y bocinas adquiridas pero sin cablear (requiere soldado de headers a la Pi Zero 2W).

4. **Sin sincronización bidireccional** — la Pi escribe a Firestore pero no lee los alumnos del `scanner-v3`. La BD local SQLite está separada. Esto es intencional para la fase 1 (demo) pero debe unificarse en Bloque B.

5. **Sin integración con ESP32 v8.3 PIR** — el módulo con sensores y pantalla TFT existente no está conectado aún. Requiere servidor WebSocket en la Pi.

6. **Comparación secuencial** — el match 1:N recorre alumnos uno por uno. Para más de 500 alumnos sería necesario usar estructuras tipo FAISS o Annoy.

7. **Sensibilidad a iluminación** — pruebas iniciales con luz cálida artificial; falta validar con luz natural, contraluz y bajas condiciones.

---

## Roadmap

### Corto plazo (semana del 20-26 abril 2026)

- [ ] Soldar headers 40 pines a la Raspberry Pi Zero 2W
- [ ] Conectar pantalla SPI ILI9486 con drivers fbtft o fbcp
- [ ] Conectar PAM8403 + bocinas por I2S o PWM audio
- [ ] Imprimir case 3D con branding Exara
- [ ] Integrar con ESP32 v8.3 PIR vía WebSocket (usar protocolo existente `EXITO|nombre|grupo|hora|puntual`)
- [ ] Crear script `terminal_main.py` con loop principal del kiosco
- [ ] Implementar UI minimal con Tkinter o Pygame fullscreen
- [ ] Grabar video demo para el nacional

### Mediano plazo (post-CNPyPE Nacional)

- [ ] Implementar descifrado AES-GCM-256 desde Python para leer `biometricos_seguros` del sistema web y unificar BD
- [ ] Aviso de privacidad en pantalla del kiosco al momento de captura (Art. 8 LFPDPPP)
- [ ] Portal auto-servicio de derechos ARCO para padres
- [ ] Optimización de match 1:N con índice FAISS para N > 500
- [ ] Soporte multilingüe (español + náhuatl + inglés)
- [ ] Modo offline con buffer y sincronización diferida

### Largo plazo

- [ ] Adaptación a Raspberry Pi 5 (procesador más potente, AI accelerator integrado)
- [ ] Certificación de privacidad por tercero (auditoría externa)
- [ ] Paquete Debian `.deb` instalable con un comando
- [ ] Sistema de actualización OTA
- [ ] Telemetría operativa agregada (uptime, temperatura, uso) para panel admin

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

### Licencia

Copyright © 2026 Santiago Rivera López / Exara Studio

Todos los derechos reservados. Este software y su documentación son propiedad intelectual de Santiago Rivera López / Exara Studio y están protegidos bajo los derechos de autor aplicables en los Estados Unidos Mexicanos.

Para uso académico, educativo o investigativo no-comercial contactar a contacto@exara.uk para autorización específica.

---

## Agradecimientos

- **OpenCV** — por el Model Zoo con YuNet y SFace de libre uso
- **Google Firebase** — por la infraestructura Firestore
- **Raspberry Pi Foundation** — por hardware accesible y documentación abierta
- **Comunidad open-source** — por las herramientas que hacen esto posible

---

## Versiones

- **v2.0.0-dev** (19 abril 2026) — Primera versión funcional end-to-end. Reconocimiento facial nativo + Firebase sync validados.

---

*Documento generado el 19 de abril de 2026 como parte del proceso de desarrollo de Keyon Terminal Pro v2, proyecto presentado al XXVIII Concurso Nacional de Prototipos y Proyectos de Emprendimiento (CNPyPE) 2026 — Fase Nacional.*
