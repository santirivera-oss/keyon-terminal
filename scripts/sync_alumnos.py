#!/usr/bin/env python3
"""
KEYON - Sync Alumnos desde Firebase v0.1.0
Lee alumnos activos de Firebase, identifica los NO enrolados localmente,
y permite enrolarlos uno por uno con datos auto-completados.

Uso:
    python3 sync_alumnos.py [--turno Matutino] [--grado 4] [--grupo BV]
    
Por default: turno=Matutino, grado=4, grupo=BV
"""
import cv2
import sqlite3
import numpy as np
import sys
import os
import time
import argparse
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

# === Configuracion ===
DB_PATH = "/home/keyon/keyon-terminal/db/keyon.db"
CRED_PATH = "/home/keyon/keyon-terminal/firebase-credentials.json"
MODELO_DET = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = "/home/keyon/keyon-terminal/modelos/face_recognition_sface_2021dec.onnx"
CAMERA_INDEX = 0
CAMERA_W = 640
CAMERA_H = 480
CONFIANZA_MIN = 0.85

# LCD vertical
LCD_W = 320
LCD_H = 480
WINDOW_NAME = "KEYON - Sync Alumnos"

# Logs
LOG_DIR = "/home/keyon/keyon-terminal/logs"
LOG_FILE = f"{LOG_DIR}/sync_alumnos.log"


def log(msg):
    """Log con timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(line + "\n")
    except Exception:
        pass


def conectar_firebase():
    """Inicializa Firebase Admin SDK."""
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(CRED_PATH)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        log(f"ERROR Firebase: {e}")
        return None


def obtener_matriculas_locales():
    """Retorna set de matriculas ya enroladas en SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT matricula FROM alumnos WHERE activo = 1")
        matriculas = set(row[0] for row in cursor.fetchall())
        conn.close()
        return matriculas
    except Exception as e:
        log(f"ERROR SQLite: {e}")
        return set()


def obtener_alumnos_firebase(db, turno, grado, grupo=None):
    """Obtiene alumnos de Firebase con filtros."""
    try:
        # Query con indice existente: turno + grado
        query = db.collection("alumnos") \
                  .where("turno", "==", turno) \
                  .where("grado", "==", grado) \
                  .where("estatus", "==", "activo")
        
        # Si especifica grupo, filtramos cliente-side (no romper indice)
        docs = query.stream()
        alumnos = []
        for doc in docs:
            data = doc.to_dict()
            data["_doc_id"] = doc.id  # control = doc.id
            
            # Filtrar por grupo si aplica
            if grupo and data.get("grupo") != grupo:
                continue
            
            alumnos.append(data)
        
        return alumnos
    except Exception as e:
        log(f"ERROR query Firebase: {e}")
        return []


def encontrar_camara():
    """Abre camara con V4L2 backend."""
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    if cap.isOpened():
        ret, _ = cap.read()
        if ret:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
            return cap
    cap.release()
    return None


def adaptar_para_lcd(frame_bgr):
    """Rota y centra frame para LCD vertical."""
    rotado = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
    h_rot, w_rot = rotado.shape[:2]
    escala = min(LCD_W / w_rot, LCD_H / h_rot)
    nuevo_w = int(w_rot * escala)
    nuevo_h = int(h_rot * escala)
    redim = cv2.resize(rotado, (nuevo_w, nuevo_h), interpolation=cv2.INTER_AREA)
    
    canvas = np.zeros((LCD_H, LCD_W, 3), dtype=np.uint8)
    offset_x = (LCD_W - nuevo_w) // 2
    offset_y = (LCD_H - nuevo_h) // 2
    canvas[offset_y:offset_y+nuevo_h, offset_x:offset_x+nuevo_w] = redim
    
    return canvas


def configurar_ventana():
    """Configura ventana fullscreen."""
    cv2.namedWindow(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW_NAME, 
                          cv2.WND_PROP_FULLSCREEN, 
                          cv2.WINDOW_FULLSCREEN)


def capturar_rostro(detector, alumno):
    """Captura rostro desde camara live."""
    nombre_completo = f"{alumno.get('nombre', '')} {alumno.get('apellidos', '')}".strip()
    
    cap = encontrar_camara()
    if cap is None:
        log("ERROR: No se pudo abrir camara")
        return None, None
    
    print("\n" + "-" * 50)
    print(f"  Enrolando: {nombre_completo}")
    print(f"  Control:   {alumno['_doc_id']}")
    print(f"  Grupo:     {alumno.get('grado')} {alumno.get('grupo')}")
    print("-" * 50)
    print("\nINSTRUCCIONES:")
    print("  - Mira directo a la camara")
    print("  - Buena iluminacion")
    print("  - Espera bbox VERDE estable")
    print("\nCONTROLES:")
    print("  SPACE - Capturar")
    print("  ESC   - Saltar este alumno")
    print("\nIniciando preview...\n")
    time.sleep(2)
    
    detector.setInputSize((CAMERA_W, CAMERA_H))
    configurar_ventana()
    
    frame_capturado = None
    rostro_capturado = None
    contador_estable = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        _, rostros = detector.detect(frame)
        display = frame.copy()
        rostro_actual = None
        confianza_actual = 0.0
        
        if rostros is not None and len(rostros) > 0:
            rostro = max(rostros, key=lambda r: r[-1])
            x, y, w, h = rostro[:4].astype(int)
            confianza_actual = float(rostro[-1])
            
            if confianza_actual >= CONFIANZA_MIN:
                color = (0, 255, 0)
                contador_estable += 1
                rostro_actual = rostro
            else:
                color = (0, 165, 255)
                contador_estable = 0
            
            cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)
            cv2.putText(display, f"{confianza_actual:.0%}", (x, y-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        else:
            contador_estable = 0
        
        if contador_estable >= 5:
            status = "LISTO - SPACE"
            status_color = (0, 255, 0)
        elif rostro_actual is not None:
            status = f"Estable {contador_estable}/5"
            status_color = (0, 255, 255)
        else:
            status = "Acerca tu rostro"
            status_color = (0, 0, 255)
        
        cv2.putText(display, status, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        
        display_lcd = adaptar_para_lcd(display)
        cv2.putText(display_lcd, nombre_completo[:25], 
                   (10, LCD_H - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow(WINDOW_NAME, display_lcd)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            log(f"Saltado: {nombre_completo}")
            break
        elif key == 32:  # SPACE
            if rostro_actual is not None and contador_estable >= 5:
                frame_capturado = frame.copy()
                rostro_capturado = rostro_actual
                log(f"Captura: {nombre_completo} ({confianza_actual:.2%})")
                break
    
    cap.release()
    cv2.destroyAllWindows()
    
    return frame_capturado, rostro_capturado


def guardar_alumno(frame, rostro, alumno, reconocedor):
    """Guarda alumno en SQLite con datos de Firebase."""
    try:
        rostro_alineado = reconocedor.alignCrop(frame, rostro)
        embedding = reconocedor.feature(rostro_alineado)
        embedding_bytes = embedding.tobytes()
        
        # Construir nombre completo y grupo desde Firebase
        nombre = f"{alumno.get('nombre', '')} {alumno.get('apellidos', '')}".strip()
        grado = alumno.get('grado', '')
        grupo_letra = alumno.get('grupo', '')
        grupo_completo = f"{grado}{grupo_letra}"  # ej: "4BV"
        matricula = alumno['_doc_id']
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alumnos (nombre, grupo, matricula, embedding, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (nombre, grupo_completo, matricula, embedding_bytes))
        
        alumno_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        log(f"Guardado: {nombre} (ID={alumno_id}, Mat={matricula})")
        return alumno_id
    except Exception as e:
        log(f"ERROR guardando: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turno", default="Matutino", help="Matutino o Vespertino")
    parser.add_argument("--grado", default="4", help="1-6")
    parser.add_argument("--grupo", default="BV", help="BV, A, M, etc (opcional)")
    args = parser.parse_args()
    
    log("=" * 50)
    log("KEYON Sync Alumnos v0.1.0")
    log("=" * 50)
    log(f"Filtros: turno={args.turno}, grado={args.grado}, grupo={args.grupo}")
    
    # 1. Conectar Firebase
    log("Conectando a Firebase...")
    db = conectar_firebase()
    if db is None:
        log("ERROR: No se pudo conectar a Firebase")
        sys.exit(1)
    log("Firebase conectado")
    
    # 2. Obtener alumnos de Firebase
    log("Consultando alumnos en Firebase...")
    alumnos_fb = obtener_alumnos_firebase(db, args.turno, args.grado, args.grupo)
    log(f"Alumnos en Firebase (filtrados): {len(alumnos_fb)}")
    
    if len(alumnos_fb) == 0:
        log("No hay alumnos que coincidan con los filtros")
        sys.exit(0)
    
    # 3. Obtener matriculas locales
    matriculas_locales = obtener_matriculas_locales()
    log(f"Alumnos enrolados localmente: {len(matriculas_locales)}")
    
    # 4. Identificar pendientes
    pendientes = [a for a in alumnos_fb if a['_doc_id'] not in matriculas_locales]
    log(f"Pendientes de enrolar: {len(pendientes)}")
    
    if len(pendientes) == 0:
        log("No hay alumnos pendientes. Ya estan todos enrolados.")
        sys.exit(0)
    
    # 5. Mostrar lista
    print("\n" + "=" * 50)
    print(f"  ALUMNOS PENDIENTES DE ENROLAR ({len(pendientes)})")
    print("=" * 50)
    for i, a in enumerate(pendientes, 1):
        nombre = f"{a.get('nombre', '')} {a.get('apellidos', '')}".strip()
        print(f"  {i}. {nombre} ({a.get('grado')}{a.get('grupo')} - {a['_doc_id']})")
    print("=" * 50)
    
    # 6. Cargar modelos
    log("Cargando modelos AI...")
    detector = cv2.FaceDetectorYN.create(
        MODELO_DET, "", (CAMERA_W, CAMERA_H), score_threshold=0.6
    )
    reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")
    log("Modelos cargados")
    
    # 7. Loop interactivo
    enrolados = 0
    saltados = 0
    
    for alumno in pendientes:
        nombre = f"{alumno.get('nombre', '')} {alumno.get('apellidos', '')}".strip()
        
        print(f"\n>>> Siguiente: {nombre}")
        respuesta = input("Enrolar? (s/n/exit): ").strip().lower()
        
        if respuesta in ('exit', 'quit', 'salir'):
            print("Saliendo...")
            break
        
        if respuesta not in ('s', 'si', 'y', 'yes'):
            saltados += 1
            print(f"  Saltado.")
            continue
        
        # Capturar
        frame, rostro = capturar_rostro(detector, alumno)
        if frame is None or rostro is None:
            saltados += 1
            print(f"  Captura cancelada.")
            continue
        
        # Confirmar
        confirmar = input("Guardar? (s/n): ").strip().lower()
        if confirmar not in ('s', 'si', 'y', 'yes'):
            saltados += 1
            print(f"  Descartado.")
            continue
        
        # Guardar
        alumno_id = guardar_alumno(frame, rostro, alumno, reconocedor)
        if alumno_id:
            enrolados += 1
            print(f"  ENROLADO: ID={alumno_id}")
        else:
            print(f"  ERROR al guardar")
    
    # 8. Resumen
    print("\n" + "=" * 50)
    print(f"  RESUMEN")
    print("=" * 50)
    print(f"  Enrolados:  {enrolados}")
    print(f"  Saltados:   {saltados}")
    print(f"  Pendientes: {len(pendientes) - enrolados}")
    print("=" * 50)
    log(f"Sesion: enrolados={enrolados}, saltados={saltados}")


if __name__ == "__main__":
    main()
