#!/usr/bin/env python3
"""
KEYON Terminal Pro v2 - UI Kiosk con Firebase
Versión 0.4.0 - Schema corregido para panel admin web
"""
import cv2
import sqlite3
import numpy as np
import time
import sys
import os
import wave
import socket
import subprocess
import threading
import tkinter as tk
from tkinter import Label, Frame
from PIL import Image, ImageTk
from datetime import datetime, time as dtime

import firebase_admin
from firebase_admin import credentials, firestore

# === Configuración ===
BASE_DIR = "/home/keyon/keyon-terminal"
DB_PATH = f"{BASE_DIR}/db/keyon.db"
MODELO_DET = f"{BASE_DIR}/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = f"{BASE_DIR}/modelos/face_recognition_sface_2021dec.onnx"
CRED_PATH = f"{BASE_DIR}/firebase-credentials.json"

DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 480
CAM_WIDTH = 640
CAM_HEIGHT = 480
DETECT_EVERY_N_FRAMES = 3

UMBRAL_COSENO = 0.363
UMBRAL_L2 = 1.128
COOLDOWN_SECONDS = 60

TERMINAL_ID = "keyon-pi4-01"
ESCUELA = "CBTis No. 001"
COLECCION = "ingresos_cbtis"
COLECCION_STATUS = "terminal_status"
HEARTBEAT_INTERVAL = 300
VERSION_TERMINAL = "2.0.8-pi4-voice"

SOUND_ENABLED = True
SOUND_MATCH = "/tmp/keyon_match.wav"
SOUND_NOMATCH = "/tmp/keyon_nomatch.wav"

COLOR_BG = "#0a0a1a"
COLOR_HEADER = "#1a1a3a"
COLOR_TEXT = "#ffffff"
COLOR_SUCCESS = "#00ff88"
COLOR_DETECT = "#00ffff"
COLOR_ERROR = "#ff3344"
COLOR_WARN = "#ffaa00"
COLOR_BBOX_MATCH = (0, 255, 136)
COLOR_BBOX_NO_MATCH = (0, 68, 255)

detector = None
reconocedor = None
cap = None
db_firestore = None
firebase_ok = False
alumnos_db = []
ultimo_match = {}
ultimo_sonido_nomatch = 0
ultimo_heartbeat = 0
frame_count = 0
last_detection = None


def generar_tono(frecuencias, duracion=0.15, sample_rate=44100, volumen=0.4):
    t_per_freq = duracion / len(frecuencias)
    samples_per_freq = int(t_per_freq * sample_rate)
    audio = np.array([], dtype=np.int16)
    for freq in frecuencias:
        t = np.linspace(0, t_per_freq, samples_per_freq, False)
        onda = np.sin(2 * np.pi * freq * t)
        envelope = np.ones(samples_per_freq)
        fade = int(0.01 * sample_rate)
        envelope[:fade] = np.linspace(0, 1, fade)
        envelope[-fade:] = np.linspace(1, 0, fade)
        onda = onda * envelope * volumen
        audio = np.concatenate([audio, (onda * 32767).astype(np.int16)])
    return audio, sample_rate


def guardar_wav(audio, sample_rate, path):
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())


def reproducir_sonido(path):
    if not SOUND_ENABLED or not os.path.exists(path):
        return
    def _play():
        try:
            subprocess.Popen(['pw-play', path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def generar_sonidos():
    print("Generando sonidos...")
    audio_match, sr = generar_tono([800, 1200], duracion=0.25)
    guardar_wav(audio_match, sr, SOUND_MATCH)
    audio_nomatch, sr = generar_tono([400, 250], duracion=0.30)
    guardar_wav(audio_nomatch, sr, SOUND_NOMATCH)
    print("Sonidos OK")



# === Voz TTS (espeak-ng) ===
ultimo_voz_match = {}
ultimo_voz_nomatch = 0
SOUND_VOZ_NOMATCH = "/tmp/keyon_voz_nomatch.wav"


def obtener_saludo_hora():
    """Devuelve saludo segun hora del dia."""
    h = datetime.now().hour
    if 6 <= h < 12:
        return "Buenos dias"
    elif 12 <= h < 19:
        return "Buenas tardes"
    else:
        return "Buenas noches"


def generar_voz_match(primer_nombre):
    """Genera WAV con saludo personalizado para el alumno."""
    saludo = obtener_saludo_hora()
    texto = f"{saludo}, bienvenido {primer_nombre}"
    path = f"/tmp/keyon_voz_{primer_nombre.lower().replace(' ', '_')}.wav"
    try:
        subprocess.run(
            ["espeak-ng", "-v", "es-mx", "-s", "135", "-w", path, texto],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return path
    except Exception as e:
        print(f"  TTS ERROR: {e}")
        return None


def generar_voz_nomatch_wav():
    """Pre-genera el WAV de denegado al inicio."""
    texto = "Rostro no identificado, acuda con administracion"
    try:
        subprocess.run(
            ["espeak-ng", "-v", "es-mx", "-s", "135", "-w", SOUND_VOZ_NOMATCH, texto],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("Voz denegado OK")
    except Exception as e:
        print(f"Voz denegado ERROR: {e}")


def reproducir_voz(path):
    """Reproduce WAV con pw-play en thread separado."""
    if not path or not os.path.exists(path):
        return
    def _play():
        try:
            subprocess.Popen(['pw-play', path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()



def obtener_temp_cpu():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def inicializar_firebase():
    global db_firestore, firebase_ok
    try:
        if not os.path.exists(CRED_PATH):
            print(f"WARN: No existe {CRED_PATH}")
            firebase_ok = False
            return False
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        db_firestore = firestore.client()
        firebase_ok = True
        print("Firebase OK")
        return True
    except Exception as e:
        print(f"ERROR Firebase: {e}")
        firebase_ok = False
        return False


def determinar_turno():
    ahora = datetime.now().time()
    if dtime(6, 0) <= ahora < dtime(14, 0):
        return "matutino"
    return "vespertino"


def determinar_estado(turno):
    ahora = datetime.now().time()
    if turno == "matutino":
        if ahora < dtime(7, 15):
            return "puntual"
        elif ahora < dtime(7, 30):
            return "retardo"
        else:
            return "falta"
    else:
        if ahora < dtime(14, 15):
            return "puntual"
        elif ahora < dtime(14, 30):
            return "retardo"
        else:
            return "falta"


def deducir_grado_aula(grupo):
    """Deduce grado y aula a partir del grupo. Ej: 4BV -> ('4°B', '4BV')"""
    if grupo and len(grupo) >= 2:
        numero = grupo[0]
        letra = grupo[1]
        grado = f"{numero}°{letra}"
        return grado, grupo
    return "?", grupo or "?"


def construir_documento(alumno, score_c, score_l2):
    """Schema completo compatible con panel admin web."""
    ahora = datetime.now()
    turno = determinar_turno()
    estado = determinar_estado(turno)
    grado, aula = deducir_grado_aula(alumno["grupo"])
    return {
        "aula": aula,
        "dispositivo": "Raspberry Pi 4 Model B",
        "escuela": ESCUELA,
        "estadoLlegada": estado,
        "fecha": ahora.strftime("%Y-%m-%d"),
        "fotoUrl": None,
        "grado": grado,
        "grupo": alumno["grupo"],
        "hora": ahora.strftime("%H:%M:%S"),
        "identificador": alumno["matricula"],
        "metodoVerificacion": "facial_local_terminal",
        "modo": "facial",
        "nombre": alumno["nombre"],
        "origen": "terminal_pi",
        "procesadoEnDispositivo": True,
        "scoreCosine": float(score_c),
        "scoreL2": float(score_l2),
        "sincronizadoFirebase": True,
        "terminalId": TERMINAL_ID,
        "timestamp": ahora.isoformat(),
        "tipoPersona": "Alumno",
        "tipoRegistro": "Ingreso",
        "turno": turno,
        "versionTerminal": VERSION_TERMINAL
    }


def escribir_match_firebase(alumno, cos, l2):
    if not firebase_ok or db_firestore is None:
        return
    def _write():
        try:
            doc = construir_documento(alumno, cos, l2)
            ref = db_firestore.collection(COLECCION).add(doc)
            doc_id = ref[1].id
            print(f"  Firebase OK: {doc_id}")
        except Exception as e:
            print(f"  Firebase ERROR: {e}")
    threading.Thread(target=_write, daemon=True).start()


def enviar_heartbeat():
    if not firebase_ok or db_firestore is None:
        return False
    try:
        data = {
            "terminalId": TERMINAL_ID,
            "estado": "online",
            "ultimoHeartbeat": firestore.SERVER_TIMESTAMP,
            "temperaturaCpu": obtener_temp_cpu(),
            "ultimaIp": obtener_ip_local(),
            "dispositivo": "Raspberry Pi 4 Model B",
            "escuela": ESCUELA,
            "version": VERSION_TERMINAL
        }
        db_firestore.collection(COLECCION_STATUS).document(TERMINAL_ID).set(
            data, merge=True
        )
        return True
    except Exception as e:
        print(f"Heartbeat ERROR: {e}")
        return False


print("=" * 60)
print(f"  KEYON Terminal UI v{VERSION_TERMINAL}")
print("=" * 60)

generar_sonidos()
generar_voz_nomatch_wav()
inicializar_firebase()

print("Cargando modelos...")
detector = cv2.FaceDetectorYN.create(MODELO_DET, "", (CAM_WIDTH, CAM_HEIGHT),
                                      score_threshold=0.6)
reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")
print("Modelos cargados OK")

print("Conectando cámara...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: No pude abrir la cámara")
    sys.exit(1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)
print(f"Camara abierta a {CAM_WIDTH}x{CAM_HEIGHT}")

print("Cargando alumnos desde BD local...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, nombre, grupo, matricula, embedding FROM alumnos WHERE activo=1")
for row in cursor.fetchall():
    aid, nombre, grupo, matricula, emb_bytes = row
    embedding = np.frombuffer(emb_bytes, dtype=np.float32).reshape(1, 128)
    alumnos_db.append({"id": aid, "nombre": nombre, "grupo": grupo,
                       "matricula": matricula, "embedding": embedding})
conn.close()
print(f"{len(alumnos_db)} alumnos en memoria")

if firebase_ok:
    if enviar_heartbeat():
        print("Heartbeat inicial enviado")
        ultimo_heartbeat = time.time()

print("Warm-up camara (3 segundos)...")
for _ in range(20):
    cap.read()
print("Camara lista")


root = tk.Tk()
root.title("KEYON Terminal")
root.configure(bg=COLOR_BG)
root.geometry(f"{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}+0+0")
root.overrideredirect(True)

header = Frame(root, bg=COLOR_HEADER, height=40)
header.pack(fill="x", side="top")
header.pack_propagate(False)

label_titulo = Label(header, text="KEYON · CBTis 001",
                     bg=COLOR_HEADER, fg=COLOR_TEXT,
                     font=("Helvetica", 11, "bold"))
label_titulo.pack(side="left", padx=8, pady=8)

label_status = Label(header, text="● 00°C",
                     bg=COLOR_HEADER, fg=COLOR_SUCCESS,
                     font=("Helvetica", 9))
label_status.pack(side="left", padx=4, pady=8)

label_fb = Label(header, text="☁",
                 bg=COLOR_HEADER, fg=COLOR_WARN,
                 font=("Helvetica", 9, "bold"))
label_fb.pack(side="left", padx=2, pady=8)

label_hora = Label(header, text="00:00:00",
                   bg=COLOR_HEADER, fg=COLOR_TEXT,
                   font=("Helvetica", 10))
label_hora.pack(side="right", padx=8, pady=8)

video_frame = Frame(root, bg=COLOR_BG)
video_frame.pack(fill="both", expand=True)
label_video = Label(video_frame, bg="#000")
label_video.pack(fill="both", expand=True)

footer = Frame(root, bg=COLOR_HEADER, height=90)
footer.pack(fill="x", side="bottom")
footer.pack_propagate(False)

label_estado = Label(footer, text="Esperando rostro...",
                     bg=COLOR_HEADER, fg=COLOR_TEXT,
                     font=("Helvetica", 12, "bold"))
label_estado.pack(pady=(8, 2))

label_detalle = Label(footer, text="",
                      bg=COLOR_HEADER, fg=COLOR_DETECT,
                      font=("Helvetica", 9))
label_detalle.pack(pady=(0, 2))

label_score = Label(footer, text="",
                    bg=COLOR_HEADER, fg=COLOR_TEXT,
                    font=("Courier", 8))
label_score.pack(pady=(0, 4))


def identificar_rostro(imagen, rostro):
    rostro_alineado = reconocedor.alignCrop(imagen, rostro)
    embedding_actual = reconocedor.feature(rostro_alineado)
    mejor_match = None
    mejor_cos = 0
    mejor_l2 = 999
    for alumno in alumnos_db:
        cos = reconocedor.match(embedding_actual, alumno["embedding"],
                                cv2.FaceRecognizerSF_FR_COSINE)
        l2 = reconocedor.match(embedding_actual, alumno["embedding"],
                               cv2.FaceRecognizerSF_FR_NORM_L2)
        if cos > UMBRAL_COSENO and l2 < UMBRAL_L2:
            if cos > mejor_cos:
                mejor_match = alumno
                mejor_cos = cos
                mejor_l2 = l2
    if mejor_match:
        return {"alumno": mejor_match, "cos": mejor_cos, "l2": mejor_l2}
    return None


def actualizar_frame():
    global frame_count, last_detection, ultimo_sonido_nomatch, ultimo_heartbeat
    
    ret, frame = cap.read()
    if not ret:
        root.after(100, actualizar_frame)
        return
    
    frame_count += 1
    frame = cv2.flip(frame, 1)
    
    ahora_ts = time.time()
    if firebase_ok and (ahora_ts - ultimo_heartbeat) > HEARTBEAT_INTERVAL:
        threading.Thread(target=enviar_heartbeat, daemon=True).start()
        ultimo_heartbeat = ahora_ts
    
    if frame_count % DETECT_EVERY_N_FRAMES == 0:
        _, rostros = detector.detect(frame)
        if rostros is not None and len(rostros) > 0:
            rostro = rostros[0]
            confianza = rostro[-1]
            match = identificar_rostro(frame, rostro)
            
            if match:
                alumno = match["alumno"]
                ultimo = ultimo_match.get(alumno["matricula"], 0)
                if (ahora_ts - ultimo) > COOLDOWN_SECONDS:
                    ultimo_match[alumno["matricula"]] = ahora_ts
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"MATCH {alumno['nombre']} | cos={match['cos']:.3f}")
                    reproducir_sonido(SOUND_MATCH)
                    primer_nombre = alumno["nombre"].split()[0]
                    voz_path = generar_voz_match(primer_nombre)
                    # Esperar 0.4s para que termine el ding-ding antes de hablar
                    threading.Timer(0.4, reproducir_voz, args=[voz_path]).start()
                    escribir_match_firebase(alumno, match["cos"], match["l2"])
                
                last_detection = {"tipo": "match", "rostro": rostro,
                                  "alumno": alumno, "cos": match["cos"],
                                  "l2": match["l2"], "confianza": confianza,
                                  "timestamp": time.time()}
            else:
                if (ahora_ts - ultimo_sonido_nomatch) > 15:
                    ultimo_sonido_nomatch = ahora_ts
                    reproducir_sonido(SOUND_NOMATCH)
                    threading.Timer(0.5, reproducir_voz, args=[SOUND_VOZ_NOMATCH]).start()
                last_detection = {"tipo": "no_match", "rostro": rostro,
                                  "confianza": confianza, "timestamp": time.time()}
        else:
            if last_detection and (time.time() - last_detection["timestamp"]) > 1.0:
                last_detection = None
    
    if last_detection and (time.time() - last_detection["timestamp"]) < 1.0:
        rostro = last_detection["rostro"]
        x, y, w, h = rostro[:4].astype(int)
        
        if last_detection["tipo"] == "match":
            color = COLOR_BBOX_MATCH
            alumno = last_detection["alumno"]
            cos = last_detection["cos"]
            l2 = last_detection["l2"]
            conf = last_detection["confianza"]
            primer_nombre = alumno['nombre'].split()[0]
            label_estado.config(text=f"✓ Bienvenido {primer_nombre}", fg=COLOR_SUCCESS)
            label_detalle.config(text=f"{alumno['grupo']} · {determinar_estado(determinar_turno())} · {datetime.now().strftime('%H:%M')}",
                                 fg=COLOR_DETECT)
            label_score.config(text=f"cos={cos:.3f}  L2={l2:.3f}  conf={conf:.2f}",
                              fg=COLOR_TEXT)
        else:
            color = COLOR_BBOX_NO_MATCH
            conf = last_detection["confianza"]
            label_estado.config(text="⚠ ACCESO DENEGADO", fg=COLOR_ERROR)
            label_detalle.config(text="Rostro no reconocido", fg=COLOR_WARN)
            label_score.config(text=f"conf={conf:.2f}  ·  acuda con admin",
                              fg=COLOR_WARN)
        
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 3)
    else:
        label_estado.config(text="Esperando rostro...", fg=COLOR_TEXT)
        label_detalle.config(text="")
        label_score.config(text="")
    
    frame_resized = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT - 130))
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    imgtk = ImageTk.PhotoImage(image=img)
    label_video.imgtk = imgtk
    label_video.configure(image=imgtk)
    
    label_hora.config(text=datetime.now().strftime("%H:%M:%S"))
    
    temp = obtener_temp_cpu()
    color_temp = COLOR_SUCCESS if temp < 65 else COLOR_WARN if temp < 75 else COLOR_ERROR
    label_status.config(text=f"● {temp:.0f}°C", fg=color_temp)
    
    if firebase_ok:
        label_fb.config(text="☁", fg=COLOR_SUCCESS)
    else:
        label_fb.config(text="☁", fg=COLOR_ERROR)
    
    root.after(100, actualizar_frame)


def salir(event=None):
    print("\nCerrando...")
    cap.release()
    root.destroy()
    sys.exit(0)


root.bind("<Escape>", salir)
root.bind("q", salir)
root.bind("Q", salir)

print("Iniciando UI...")
print("Presiona ESC o Q para salir")
print("=" * 60)
root.after(500, actualizar_frame)
root.mainloop()
