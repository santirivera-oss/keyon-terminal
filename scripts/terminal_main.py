#!/usr/bin/env python3
"""
KEYON Terminal Pro v2 - Main Loop
Fase 1.4 - Logs + errores robustos + heartbeat a Firebase

Uso:
    python3 terminal_main.py              # modo real
    python3 terminal_main.py --dry-run    # modo demo
    python3 terminal_main.py --debug      # logs mas verbosos
"""

import cv2
import sqlite3
import numpy as np
import subprocess
import time
import sys
import os
import socket
import shutil
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, time as dtime

import firebase_admin
from firebase_admin import credentials, firestore

# === CLI args ===
DRY_RUN = "--dry-run" in sys.argv or "--demo" in sys.argv
DEBUG = "--debug" in sys.argv

# === Configuracion ===
BASE_DIR = "/home/keyon/keyon-terminal"
DB_PATH = f"{BASE_DIR}/db/keyon.db"
MODELO_DET = f"{BASE_DIR}/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = f"{BASE_DIR}/modelos/face_recognition_sface_2021dec.onnx"
CRED_PATH = f"{BASE_DIR}/firebase-credentials.json"
LOG_DIR = f"{BASE_DIR}/logs"
LOG_FILE = f"{LOG_DIR}/kiosco.log"
FRAME_TEMP = "/tmp/keyon_frame.jpg"

UMBRAL_COSENO = 0.363
UMBRAL_L2 = 1.128
INTERVALO = 3
COOLDOWN_MISMO_ALUMNO = 60
TERMINAL_ID = "keyon-pi4-01"
HEARTBEAT_INTERVAL = 300  # cada 5 minutos
ESCUELA = "CBTis No. 001"
COLECCION = "ingresos_cbtis"
COLECCION_STATUS = "terminal_status"
VERSION = "2.0.3-dev"

MAX_FALLOS_CONSECUTIVOS = 5
BACKOFF_INICIAL = 1
BACKOFF_MAX = 30

TOLERANCIA_MATUTINO = dtime(7, 15, 0)
LIMITE_MATUTINO = dtime(8, 0, 0)
TOLERANCIA_VESPERTINO = dtime(13, 25, 0)
LIMITE_VESPERTINO = dtime(14, 0, 0)

LETRAS_MATUTINO = set("ABCDEF")
LETRAS_VESPERTINO = set("GHIJKLM")

# === Setup logging ===
os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger("keyon")
log.setLevel(logging.DEBUG if DEBUG else logging.INFO)

file_handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", interval=1, backupCount=30, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(message)s"))
console_handler.setLevel(logging.INFO)

log.addHandler(file_handler)
log.addHandler(console_handler)

# === Utilidades ===

def determinar_turno(alumno_turno=None, grupo=None):
    if alumno_turno and alumno_turno.strip():
        return alumno_turno.strip().lower()
    if grupo and len(grupo) >= 2:
        letra = grupo[1].upper()
        if letra in LETRAS_MATUTINO:
            return "matutino"
        if letra in LETRAS_VESPERTINO:
            return "vespertino"
    hora = datetime.now().time()
    if dtime(7, 0) <= hora < dtime(14, 0):
        return "matutino"
    if dtime(13, 10) <= hora <= dtime(20, 10):
        return "vespertino"
    return "matutino"

def determinar_estado_llegada(turno, tipo_registro):
    if tipo_registro != "Ingreso":
        return None
    hora = datetime.now().time()
    if turno == "matutino":
        if hora <= TOLERANCIA_MATUTINO:
            return "puntual"
        elif hora <= LIMITE_MATUTINO:
            return "retardo"
        else:
            return "tarde"
    else:
        if hora <= TOLERANCIA_VESPERTINO:
            return "puntual"
        elif hora <= LIMITE_VESPERTINO:
            return "retardo"
        else:
            return "tarde"

def extraer_grado(grupo):
    if not grupo or len(grupo) < 2:
        return ""
    return f"{grupo[0]}°{grupo[1]}"

def temperatura_cpu():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None

def obtener_info_sistema():
    """Info para heartbeat: RAM, disco, uptime, IP local"""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = int([l for l in lines if "MemTotal" in l][0].split()[1])
        mem_free = int([l for l in lines if "MemAvailable" in l][0].split()[1])
        info["ramUsadaMB"] = (mem_total - mem_free) // 1024
    except Exception:
        info["ramUsadaMB"] = 0

    try:
        _, _, libre = shutil.disk_usage("/")
        info["espacioDiscoLibreGB"] = round(libre / (1024**3), 1)
    except Exception:
        info["espacioDiscoLibreGB"] = 0

    try:
        with open("/proc/uptime") as f:
            info["uptimeSegundos"] = int(float(f.read().split()[0]))
    except Exception:
        info["uptimeSegundos"] = 0

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        info["ip"] = "unknown"

    return info

# === Inicializacion con logs ===
banner = "DRY-RUN" if DRY_RUN else "PRODUCCION"
log.info("=" * 60)
log.info(f"  KEYON Terminal Pro v2 - Kiosco v{VERSION} [{banner}]")
log.info("=" * 60)
log.info(f"  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log.info(f"  Terminal ID: {TERMINAL_ID}")
log.info(f"  Escuela: {ESCUELA}")
log.info(f"  Coleccion: {COLECCION}")
log.info(f"  Heartbeat cada: {HEARTBEAT_INTERVAL}s")
log.info(f"  Log file: {LOG_FILE}")
temp_inicio = temperatura_cpu()
if temp_inicio:
    log.info(f"  CPU temp: {temp_inicio:.1f} C")

if DRY_RUN:
    log.warning("  MODO DRY-RUN: no escribira a Firebase")

if DEBUG:
    log.debug("  MODO DEBUG activado")

log.info("")
log.info("  Cargando YuNet + SFace...")
try:
    detector = cv2.FaceDetectorYN.create(MODELO_DET, "", (640, 480),
                                          score_threshold=0.6)
    reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")
    log.info("  Modelos cargados OK")
except Exception as e:
    log.error(f"  ERROR cargando modelos: {e}")
    sys.exit(1)

log.info("  Cargando alumnos desde BD local...")
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, grupo, matricula, embedding FROM alumnos WHERE activo=1")
    ALUMNOS = []
    for row in cursor.fetchall():
        aid, nombre, grupo, matricula, emb_blob = row
        emb = np.frombuffer(emb_blob, dtype=np.float32).reshape(1, 128)
        ALUMNOS.append({
            "id": aid, "nombre": nombre, "grupo": grupo,
            "matricula": matricula, "turno": None, "embedding": emb
        })
    conn.close()
    log.info(f"  {len(ALUMNOS)} alumnos en memoria")
except Exception as e:
    log.error(f"  ERROR leyendo BD: {e}")
    sys.exit(1)

if not ALUMNOS:
    log.error("  No hay alumnos registrados. Aborta.")
    sys.exit(1)

db = None
firebase_ok = False
if not DRY_RUN:
    log.info("  Conectando Firebase...")
    try:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        firebase_ok = True
        log.info(f"  Firebase OK - Proyecto: {db.project}")
    except Exception as e:
        log.error(f"  Firebase ERROR: {e}")
        log.warning("  Modo OFFLINE (solo BD local)")
        firebase_ok = False
else:
    log.info("  Firebase SKIPPED (dry-run)")

ultimo_registro = {}

# === Funciones core ===

def capturar_frame():
    cmd = [
        "ffmpeg", "-f", "v4l2", "-video_size", "640x480",
        "-i", "/dev/video0", "-vf", "select='eq(n,15)'",
        "-frames:v", "1", "-update", "1", "-y",
        FRAME_TEMP, "-loglevel", "quiet"
    ]
    try:
        subprocess.run(cmd, check=True, timeout=10)
        return True
    except subprocess.TimeoutExpired:
        log.warning("Timeout ffmpeg (10s)")
        return False
    except subprocess.CalledProcessError as e:
        log.warning(f"ffmpeg fallo con codigo {e.returncode}")
        return False
    except FileNotFoundError:
        log.error("ffmpeg no esta instalado")
        return False
    except Exception as e:
        log.warning(f"Captura fallo: {e}")
        return False

def identificar_rostro(imagen):
    try:
        h, w = imagen.shape[:2]
        detector.setInputSize((w, h))
        _, rostros = detector.detect(imagen)
        if rostros is None or len(rostros) == 0:
            return None
        rostro = rostros[0]
        alineado = reconocedor.alignCrop(imagen, rostro)
        emb_nuevo = reconocedor.feature(alineado)
    except cv2.error as e:
        log.warning(f"OpenCV error: {e}")
        return None
    except Exception as e:
        log.warning(f"Error en identificacion: {e}")
        return None

    mejor, mejor_cos, mejor_l2 = None, 0.0, 999.0
    for alumno in ALUMNOS:
        try:
            sc = reconocedor.match(emb_nuevo, alumno["embedding"],
                                    cv2.FaceRecognizerSF_FR_COSINE)
            sl = reconocedor.match(emb_nuevo, alumno["embedding"],
                                    cv2.FaceRecognizerSF_FR_NORM_L2)
            if sc > mejor_cos:
                mejor_cos, mejor_l2, mejor = sc, sl, alumno
        except Exception as e:
            log.debug(f"Match fallo para {alumno['nombre']}: {e}")
            continue

    if mejor and mejor_cos > UMBRAL_COSENO and mejor_l2 < UMBRAL_L2:
        return (mejor, mejor_cos, mejor_l2)
    return None

def construir_documento(alumno, score_c, score_l2):
    ahora = datetime.now()
    tipo_registro = "Ingreso"
    turno = determinar_turno(alumno.get("turno"), alumno["grupo"])
    estado = determinar_estado_llegada(turno, tipo_registro)
    return {
        "tipoPersona": "Alumno",
        "nombre": alumno["nombre"],
        "identificador": alumno["matricula"],
        "aula": alumno["grupo"],
        "grado": extraer_grado(alumno["grupo"]),
        "grupo": alumno["grupo"],
        "turno": turno,
        "estadoLlegada": estado,
        "tipoRegistro": tipo_registro,
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M:%S"),
        "modo": "facial",
        "timestamp": ahora.isoformat(),
        "fotoUrl": None,
        "escuela": ESCUELA,
        "origen": "terminal_pi",
        "terminalId": TERMINAL_ID,
        "dispositivo": "Raspberry Pi 4 Model B",
        "metodoVerificacion": "facial_local_terminal",
        "scoreCosine": float(score_c),
        "scoreL2": float(score_l2),
        "procesadoEnDispositivo": True,
        "sincronizadoFirebase": True,
        "versionTerminal": VERSION
    }

def registrar_local(alumno_id, tipo, score_c, score_l2):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO asistencias
            (alumno_id, tipo, score_cosine, score_l2, sincronizado_firebase)
            VALUES (?, ?, ?, ?, ?)
        """, (alumno_id, tipo, score_c, score_l2, 0))
        asistencia_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return asistencia_id
    except Exception as e:
        log.error(f"Error guardando local: {e}")
        return None

def registrar_firebase(doc):
    if DRY_RUN or not firebase_ok:
        return None
    try:
        _, doc_ref = db.collection(COLECCION).add(doc)
        return doc_ref.id
    except Exception as e:
        log.error(f"Firebase error: {e}")
        return None

def marcar_sincronizado(asistencia_id):
    if not asistencia_id:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE asistencias SET sincronizado_firebase=1 WHERE id=?",
                       (asistencia_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"No se pudo marcar sincronizado: {e}")

def esta_en_cooldown(matricula):
    if matricula not in ultimo_registro:
        return False
    transcurrido = (datetime.now() - ultimo_registro[matricula]).total_seconds()
    return transcurrido < COOLDOWN_MISMO_ALUMNO

def enviar_heartbeat(inicio_sesion, total_registros_sesion):
    """Actualiza terminal_status/{terminalId} con estado actual"""
    if DRY_RUN or not firebase_ok:
        return False
    
    try:
        ahora = datetime.now()
        info = obtener_info_sistema()
        temp = temperatura_cpu() or 0.0
        
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) FROM asistencias 
                WHERE date(timestamp) = date('now', 'localtime')
            """)
            registros_hoy = c.fetchone()[0]
            conn.close()
        except Exception:
            registros_hoy = 0
        
        doc = {
            "terminalId": TERMINAL_ID,
            "dispositivo": "Raspberry Pi 4 Model B",
            "estado": "online",
            "ultimoHeartbeat": firestore.SERVER_TIMESTAMP,
            "ultimoHeartbeatLocal": ahora.isoformat(),
            "temperaturaCpu": round(temp, 1),
            "uptimeSegundos": info["uptimeSegundos"],
            "totalRegistrosHoy": registros_hoy,
            "totalRegistrosSesion": total_registros_sesion,
            "versionTerminal": VERSION,
            "conectadoDesde": inicio_sesion.isoformat(),
            "escuela": ESCUELA,
            "ip": info["ip"],
            "ramUsadaMB": info["ramUsadaMB"],
            "espacioDiscoLibreGB": info["espacioDiscoLibreGB"],
            "origen": "terminal_pi"
        }
        
        db.collection(COLECCION_STATUS).document(TERMINAL_ID).set(doc)
        return True
    except Exception as e:
        log.warning(f"Heartbeat fallo: {e}")
        return False

# === Loop principal ===
log.info("")
log.info("=" * 60)
log.info(f"  KIOSCO ACTIVO - Ctrl+C para salir")
log.info(f"  Intervalo: {INTERVALO}s | Cooldown: {COOLDOWN_MISMO_ALUMNO}s")
log.info(f"  Heartbeat: cada {HEARTBEAT_INTERVAL}s")
log.info(f"  Max fallos consecutivos: {MAX_FALLOS_CONSECUTIVOS}")
log.info("=" * 60)
log.info("")

contador = 0
total_identificados = 0
total_registrados = 0
total_sincronizados = 0
total_cooldown = 0
total_errores = 0
total_heartbeats = 0
fallos_consecutivos = 0
backoff = BACKOFF_INICIAL

inicio_sesion = datetime.now()
ultimo_heartbeat = datetime.now()

# Heartbeat inicial
if enviar_heartbeat(inicio_sesion, total_registrados):
    total_heartbeats += 1
    log.info(f"Heartbeat inicial enviado a {COLECCION_STATUS}/{TERMINAL_ID}")

try:
    while True:
        contador += 1
        hora_str = datetime.now().strftime('%H:%M:%S')

        # Heartbeat periodico
        if (datetime.now() - ultimo_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL:
            if enviar_heartbeat(inicio_sesion, total_registrados):
                total_heartbeats += 1
                log.info(f"[{hora_str}] Heartbeat #{total_heartbeats} enviado")
                ultimo_heartbeat = datetime.now()

        try:
            t0 = time.time()
            
            if not capturar_frame():
                fallos_consecutivos += 1
                total_errores += 1
                log.warning(f"[{hora_str}] #{contador} captura fallo (consecutivos: {fallos_consecutivos}/{MAX_FALLOS_CONSECUTIVOS})")
                
                if fallos_consecutivos >= MAX_FALLOS_CONSECUTIVOS:
                    log.error(f"[{hora_str}] Muchos fallos, backoff {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX)
                else:
                    time.sleep(INTERVALO)
                continue
            
            if fallos_consecutivos > 0:
                log.info(f"[{hora_str}] Recuperado de {fallos_consecutivos} fallos")
                fallos_consecutivos = 0
                backoff = BACKOFF_INICIAL
            
            imagen = cv2.imread(FRAME_TEMP)
            if imagen is None:
                log.warning(f"[{hora_str}] #{contador} fallo lectura JPG")
                total_errores += 1
                time.sleep(INTERVALO)
                continue

            resultado = identificar_rostro(imagen)
            t_total = time.time() - t0

            if resultado is None:
                log.info(f"[{hora_str}] #{contador} sin rostro ({t_total:.1f}s)")
            else:
                alumno, cos, l2 = resultado
                total_identificados += 1

                if esta_en_cooldown(alumno["matricula"]):
                    restante = COOLDOWN_MISMO_ALUMNO - (datetime.now() - ultimo_registro[alumno["matricula"]]).total_seconds()
                    total_cooldown += 1
                    log.info(f"[{hora_str}] #{contador} {alumno['nombre']} [cooldown {restante:.0f}s]")
                else:
                    asistencia_id = registrar_local(alumno["id"], "Ingreso", cos, l2)
                    doc = construir_documento(alumno, cos, l2)

                    if DRY_RUN:
                        log.info(f"[{hora_str}] #{contador} [DRY-RUN] {alumno['nombre']} | {doc['identificador']} | turno={doc['turno']} | estado={doc['estadoLlegada']} | cos={cos:.3f} L2={l2:.3f}")
                    else:
                        doc_id = registrar_firebase(doc)
                        total_registrados += 1
                        if doc_id:
                            marcar_sincronizado(asistencia_id)
                            total_sincronizados += 1
                            log.info(f"[{hora_str}] #{contador} REGISTRO {alumno['nombre']} | {doc['identificador']} | estado={doc['estadoLlegada']} | cos={cos:.3f} | Firebase {doc_id[:10]} | {t_total:.1f}s")
                        else:
                            log.warning(f"[{hora_str}] #{contador} LOCAL SOLO {alumno['nombre']} (firebase fallo)")

                    ultimo_registro[alumno["matricula"]] = datetime.now()

            time.sleep(INTERVALO)
        
        except Exception as e:
            log.error(f"[{hora_str}] Error inesperado en ciclo #{contador}: {e}")
            total_errores += 1
            time.sleep(INTERVALO)

except KeyboardInterrupt:
    # Heartbeat final con estado offline
    if not DRY_RUN and firebase_ok:
        try:
            db.collection(COLECCION_STATUS).document(TERMINAL_ID).update({
                "estado": "offline",
                "ultimoHeartbeatLocal": datetime.now().isoformat(),
                "ultimoHeartbeat": firestore.SERVER_TIMESTAMP
            })
            log.info("Estado final: offline (enviado a Firebase)")
        except Exception as e:
            log.warning(f"No se pudo marcar offline: {e}")
    
    log.info("")
    log.info("=" * 60)
    log.info(f"  KIOSCO DETENIDO")
    log.info(f"  Total ciclos:              {contador}")
    log.info(f"  Identificaciones:          {total_identificados}")
    log.info(f"  En cooldown (no registro): {total_cooldown}")
    log.info(f"  Heartbeats enviados:       {total_heartbeats}")
    log.info(f"  Errores:                   {total_errores}")
    if not DRY_RUN:
        log.info(f"  Registros nuevos:          {total_registrados}")
        log.info(f"  Sincronizados Firebase:    {total_sincronizados}")
    else:
        log.info(f"  Modo: DRY-RUN")
    temp_fin = temperatura_cpu()
    if temp_fin:
        log.info(f"  CPU temp final:            {temp_fin:.1f} C")
    uptime = int((datetime.now() - inicio_sesion).total_seconds())
    log.info(f"  Sesion duracion:           {uptime}s ({uptime//60}m)")
    log.info(f"  Hora fin: {datetime.now().strftime('%H:%M:%S')}")
    log.info("=" * 60)
