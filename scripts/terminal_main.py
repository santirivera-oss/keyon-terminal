#!/usr/bin/env python3
"""
KEYON Terminal Pro v2 - Main Loop
Fase 1.2.1 - Schema validado con sistema web

Uso:
    python3 terminal_main.py              # modo real (escribe a Firebase)
    python3 terminal_main.py --dry-run    # modo demo (NO escribe a Firebase)
"""

import cv2
import sqlite3
import numpy as np
import subprocess
import time
import sys
from datetime import datetime, time as dtime

import firebase_admin
from firebase_admin import credentials, firestore

# === CLI args ===
DRY_RUN = "--dry-run" in sys.argv or "--demo" in sys.argv

# === Configuración ===
BASE_DIR = "/home/keyon/keyon-terminal"
DB_PATH = f"{BASE_DIR}/db/keyon.db"
MODELO_DET = f"{BASE_DIR}/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = f"{BASE_DIR}/modelos/face_recognition_sface_2021dec.onnx"
CRED_PATH = f"{BASE_DIR}/firebase-credentials.json"
FRAME_TEMP = "/tmp/keyon_frame.jpg"

UMBRAL_COSENO = 0.363
UMBRAL_L2 = 1.128
INTERVALO = 3
COOLDOWN_MISMO_ALUMNO = 60
TERMINAL_ID = "keyon-pi-zero2w-01"
ESCUELA = "CBTis No. 001"    # EXACTO como el web (con espacio y punto)
COLECCION = "ingresos_cbtis"

# Umbrales estadoLlegada (idénticos al web)
TOLERANCIA_MATUTINO = dtime(7, 15, 0)
LIMITE_MATUTINO = dtime(8, 0, 0)
TOLERANCIA_VESPERTINO = dtime(13, 25, 0)
LIMITE_VESPERTINO = dtime(14, 0, 0)

# Letras de grupo por turno (según web)
LETRAS_MATUTINO = set("ABCDEF")
LETRAS_VESPERTINO = set("GHIJKLM")

# === Utilidades de negocio ===

def determinar_turno(alumno_turno=None, grupo=None):
    """
    Prioridad (idéntica al web):
    1. alumno.turno si está definido
    2. Por letra de grupo: A-F matutino, G-M vespertino
    3. Por hora actual: 07:00-14:00 matutino, resto vespertino (matutino gana en solape)
    """
    # Prioridad 1: alumno.turno
    if alumno_turno and alumno_turno.strip():
        return alumno_turno.strip().lower()
    
    # Prioridad 2: letra del grupo
    if grupo and len(grupo) >= 2:
        letra = grupo[1].upper()
        if letra in LETRAS_MATUTINO:
            return "matutino"
        if letra in LETRAS_VESPERTINO:
            return "vespertino"
    
    # Prioridad 3: hora actual
    hora = datetime.now().time()
    if dtime(7, 0) <= hora < dtime(14, 0):
        return "matutino"
    if dtime(13, 10) <= hora <= dtime(20, 10):
        return "vespertino"
    
    # Default fuera de horario
    return "matutino"

def determinar_estado_llegada(turno, tipo_registro):
    """
    Solo calcula para Ingreso. Null en Salida.
    Umbrales idénticos al web.
    """
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
    else:  # vespertino
        if hora <= TOLERANCIA_VESPERTINO:
            return "puntual"
        elif hora <= LIMITE_VESPERTINO:
            return "retardo"
        else:
            return "tarde"

def extraer_grado(grupo):
    """'4BV' -> '4°B'"""
    if not grupo or len(grupo) < 2:
        return ""
    return f"{grupo[0]}°{grupo[1]}"

# === Inicialización ===
banner = "DRY-RUN (MODO DEMO)" if DRY_RUN else "PRODUCCION"
print("=" * 60)
print(f"  KEYON Terminal Pro v2 - Kiosco v1.2.1 [{banner}]")
print("=" * 60)
print(f"  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Terminal ID: {TERMINAL_ID}")
print(f"  Escuela: {ESCUELA}")
print(f"  Coleccion Firestore: {COLECCION}")

if DRY_RUN:
    print()
    print("  ⚠ MODO DRY-RUN: no escribira a Firebase")
    print("  ⚠ Solo imprime lo que HARIA en modo normal")

print("\n  Cargando YuNet + SFace...")
detector = cv2.FaceDetectorYN.create(MODELO_DET, "", (640, 480),
                                      score_threshold=0.6)
reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")

print("  Cargando alumnos desde BD local...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, nombre, grupo, matricula, embedding FROM alumnos WHERE activo=1")
ALUMNOS = []
for row in cursor.fetchall():
    aid, nombre, grupo, matricula, emb_blob = row
    emb = np.frombuffer(emb_blob, dtype=np.float32).reshape(1, 128)
    ALUMNOS.append({
        "id": aid,
        "nombre": nombre,
        "grupo": grupo,
        "matricula": matricula,
        "turno": None,
        "embedding": emb
    })
conn.close()
print(f"  {len(ALUMNOS)} alumnos en memoria")

if not ALUMNOS:
    print("\n  ERROR: No hay alumnos registrados.")
    sys.exit(1)

db = None
firebase_ok = False
if not DRY_RUN:
    print("  Conectando Firebase...")
    try:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        firebase_ok = True
        print(f"  Firebase OK - Proyecto: {db.project}")
    except Exception as e:
        print(f"  [!] Firebase ERROR: {e}")
        firebase_ok = False
else:
    print("  Firebase SKIPPED (dry-run)")

ultimo_registro = {}

# === Funciones core ===

def capturar_frame():
    cmd = [
        "ffmpeg", "-f", "v4l2", "-video_size", "640x480",
        "-i", "/dev/video0", "-vf", "select='eq(n,5)'",
        "-frames:v", "1", "-update", "1", "-y",
        FRAME_TEMP, "-loglevel", "quiet"
    ]
    try:
        subprocess.run(cmd, check=True, timeout=10)
        return True
    except Exception:
        return False

def identificar_rostro(imagen):
    h, w = imagen.shape[:2]
    detector.setInputSize((w, h))
    _, rostros = detector.detect(imagen)
    if rostros is None or len(rostros) == 0:
        return None
    rostro = rostros[0]
    try:
        alineado = reconocedor.alignCrop(imagen, rostro)
        emb_nuevo = reconocedor.feature(alineado)
    except Exception:
        return None
    mejor, mejor_cos, mejor_l2 = None, 0.0, 999.0
    for alumno in ALUMNOS:
        sc = reconocedor.match(emb_nuevo, alumno["embedding"],
                                cv2.FaceRecognizerSF_FR_COSINE)
        sl = reconocedor.match(emb_nuevo, alumno["embedding"],
                                cv2.FaceRecognizerSF_FR_NORM_L2)
        if sc > mejor_cos:
            mejor_cos, mejor_l2, mejor = sc, sl, alumno
    if mejor and mejor_cos > UMBRAL_COSENO and mejor_l2 < UMBRAL_L2:
        return (mejor, mejor_cos, mejor_l2)
    return None

def construir_documento(alumno, score_c, score_l2):
    """Genera el dict listo para Firestore (schema ingresos_cbtis)"""
    ahora = datetime.now()
    tipo_registro = "Ingreso"
    turno = determinar_turno(alumno.get("turno"), alumno["grupo"])
    estado = determinar_estado_llegada(turno, tipo_registro)
    
    return {
        # Schema estándar del web
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
        # Campos específicos terminal
        "origen": "terminal_pi",
        "terminalId": TERMINAL_ID,
        "dispositivo": "Raspberry Pi Zero 2W",
        "metodoVerificacion": "facial_local_terminal",
        "scoreCosine": float(score_c),
        "scoreL2": float(score_l2),
        "procesadoEnDispositivo": True,
        "sincronizadoFirebase": True,
        "versionTerminal": "2.0.1-dev"
    }

def registrar_local(alumno_id, tipo, score_c, score_l2):
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

def registrar_firebase(doc):
    """Usa .add() para ID auto-generado (igual que el web)"""
    if DRY_RUN or not firebase_ok:
        return None
    try:
        _, doc_ref = db.collection(COLECCION).add(doc)
        return doc_ref.id
    except Exception as e:
        print(f"       [!] Firebase error: {e}")
        return None

def marcar_sincronizado(asistencia_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE asistencias SET sincronizado_firebase=1 WHERE id=?",
                   (asistencia_id,))
    conn.commit()
    conn.close()

def esta_en_cooldown(matricula):
    if matricula not in ultimo_registro:
        return False
    transcurrido = (datetime.now() - ultimo_registro[matricula]).total_seconds()
    return transcurrido < COOLDOWN_MISMO_ALUMNO

# === Loop principal ===
print("\n" + "=" * 60)
print(f"  KIOSCO ACTIVO - Ctrl+C para salir")
print(f"  Intervalo: {INTERVALO}s | Cooldown: {COOLDOWN_MISMO_ALUMNO}s")
print("=" * 60 + "\n")

contador = 0
total_identificados = 0
total_registrados = 0
total_sincronizados = 0
total_cooldown = 0

try:
    while True:
        contador += 1
        hora = datetime.now().strftime('%H:%M:%S')
        print(f"[{hora}] #{contador}", end=" ", flush=True)
        
        t0 = time.time()
        if not capturar_frame():
            print("fallo captura")
            time.sleep(INTERVALO); continue
        imagen = cv2.imread(FRAME_TEMP)
        if imagen is None:
            print("fallo lectura")
            time.sleep(INTERVALO); continue
        
        resultado = identificar_rostro(imagen)
        t_total = time.time() - t0
        
        if resultado is None:
            print(f"sin rostro ({t_total:.1f}s)")
        else:
            alumno, cos, l2 = resultado
            total_identificados += 1
            
            if esta_en_cooldown(alumno["matricula"]):
                restante = COOLDOWN_MISMO_ALUMNO - (datetime.now() - ultimo_registro[alumno["matricula"]]).total_seconds()
                total_cooldown += 1
                print(f"{alumno['nombre']} [cooldown {restante:.0f}s]")
            else:
                asistencia_id = registrar_local(alumno["id"], "Ingreso", cos, l2)
                doc = construir_documento(alumno, cos, l2)
                
                if DRY_RUN:
                    print()
                    print(f"    ⚡ [DRY-RUN] se hubiera registrado:")
                    print(f"       {doc['nombre']} | {doc['identificador']} | {doc['grupo']}")
                    print(f"       turno={doc['turno']} | estado={doc['estadoLlegada']}")
                    print(f"       modo={doc['modo']} | origen={doc['origen']}")
                    print(f"       escuela={doc['escuela']}")
                    print(f"       scores: cos={cos:.3f} L2={l2:.3f}")
                    print(f"       coleccion destino: {COLECCION}")
                    print()
                else:
                    doc_id = registrar_firebase(doc)
                    total_registrados += 1
                    if doc_id:
                        marcar_sincronizado(asistencia_id)
                        total_sincronizados += 1
                        sync_str = f"✓ Firebase {doc_id[:10]}..."
                    else:
                        sync_str = "× Solo local"
                    
                    print()
                    print(f"    ✓✓ REGISTRO: {alumno['nombre']}")
                    print(f"       {doc['identificador']} | {doc['grupo']} | turno={doc['turno']} | estado={doc['estadoLlegada']}")
                    print(f"       Score: cos={cos:.3f} L2={l2:.3f}")
                    print(f"       Sync: {sync_str}")
                    print(f"       Tiempo: {t_total:.2f}s")
                    print()
                
                ultimo_registro[alumno["matricula"]] = datetime.now()
        
        time.sleep(INTERVALO)

except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print(f"  KIOSCO DETENIDO")
    print(f"  Total ciclos:              {contador}")
    print(f"  Identificaciones:          {total_identificados}")
    print(f"  En cooldown (no registro): {total_cooldown}")
    if not DRY_RUN:
        print(f"  Registros nuevos:          {total_registrados}")
        print(f"  Sincronizados Firebase:    {total_sincronizados}")
    else:
        print(f"  Modo: DRY-RUN (nada escrito a Firebase)")
    print(f"  Hora fin: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
