#!/usr/bin/env python3
"""
KEYON - Enrolar Alumno v0.2.0
Captura rostro desde camara live y lo guarda en SQLite local.
Optimizado para LCD 320x480 vertical.

Uso:
    python3 enrolar.py
    
Requisitos:
    - KEYON UI detenido (sudo systemctl stop keyon-ui.service)
    - Camara libre
"""
import cv2
import sqlite3
import numpy as np
import sys
import os
import time
from datetime import datetime

# === Configuracion ===
DB_PATH = "/home/keyon/keyon-terminal/db/keyon.db"
MODELO_DET = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = "/home/keyon/keyon-terminal/modelos/face_recognition_sface_2021dec.onnx"
CAMERA_INDEX = 0
CAMERA_W = 640
CAMERA_H = 480
CONFIANZA_MIN = 0.85
LOG_DIR = "/home/keyon/keyon-terminal/logs"
LOG_FILE = f"{LOG_DIR}/enrolar.log"

# === LCD vertical 320x480 ===
LCD_W = 320
LCD_H = 480
WINDOW_NAME = "KEYON - Enrolar"


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


def matricula_existe(matricula):
    """Verifica si una matricula ya esta en la BD."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, nombre FROM alumnos WHERE matricula = ?",
            (matricula,)
        )
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        log(f"ERROR consultando matricula: {e}")
        return None


def pedir_datos():
    """Solicita datos del alumno via prompts."""
    print("\n" + "=" * 50)
    print("  KEYON - Enrolar Alumno")
    print("=" * 50)
    
    while True:
        nombre = input("Nombre completo: ").strip()
        if len(nombre) >= 3:
            break
        print("Nombre debe tener al menos 3 caracteres")
    
    while True:
        matricula = input("Matricula: ").strip().upper()
        if len(matricula) < 3:
            print("Matricula debe tener al menos 3 caracteres")
            continue
        existente = matricula_existe(matricula)
        if existente:
            print(f"ERROR: Matricula '{matricula}' ya existe (ID={existente[0]}, "
                  f"alumno: {existente[1]})")
            continue
        break
    
    while True:
        grupo = input("Grupo (ej: 4BV): ").strip().upper()
        if len(grupo) >= 2:
            break
        print("Grupo debe tener al menos 2 caracteres")
    
    return {
        "nombre": nombre,
        "matricula": matricula,
        "grupo": grupo
    }


def encontrar_camara():
    """Intenta abrir la camara en varios indices."""
    indices = [CAMERA_INDEX, 0, 1, 2]
    for idx in indices:
        log(f"Probando camara index {idx}...")
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                log(f"Camara abierta en index {idx}")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
                return cap
        cap.release()
    return None


def adaptar_para_lcd(frame_bgr):
    """
    Convierte frame de camara (640x480 horizontal) al formato LCD (320x480 vertical).
    Rota 90 grados y mantiene la proporcion para que entre completo.
    """
    # Rotar 90 grados horario para verticalizar
    rotado = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
    # rotado ahora es 480x640 (vertical)
    
    # Calcular escala para que quepa en LCD manteniendo aspect ratio
    h_rot, w_rot = rotado.shape[:2]
    escala = min(LCD_W / w_rot, LCD_H / h_rot)
    nuevo_w = int(w_rot * escala)
    nuevo_h = int(h_rot * escala)
    
    # Redimensionar
    redimensionado = cv2.resize(rotado, (nuevo_w, nuevo_h), 
                                 interpolation=cv2.INTER_AREA)
    
    # Crear canvas LCD negro y centrar imagen
    canvas = np.zeros((LCD_H, LCD_W, 3), dtype=np.uint8)
    offset_x = (LCD_W - nuevo_w) // 2
    offset_y = (LCD_H - nuevo_h) // 2
    canvas[offset_y:offset_y+nuevo_h, offset_x:offset_x+nuevo_w] = redimensionado
    
    return canvas


def configurar_ventana():
    """Configura ventana fullscreen para LCD."""
    cv2.namedWindow(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW_NAME, 
                          cv2.WND_PROP_FULLSCREEN, 
                          cv2.WINDOW_FULLSCREEN)


def capturar_rostro(detector, datos):
    """Captura rostro desde camara live. Retorna frame + rostro o None."""
    cap = encontrar_camara()
    if cap is None:
        log("ERROR: No se pudo abrir ninguna camara")
        return None, None
    
    print("\n" + "-" * 50)
    print(f"  Enrolando: {datos['nombre']}")
    print(f"  Matricula: {datos['matricula']}  Grupo: {datos['grupo']}")
    print("-" * 50)
    print("\nINSTRUCCIONES:")
    print("  - Mira directo a la camara")
    print("  - Buena iluminacion")
    print("  - Cara despejada (sin lentes oscuros)")
    print("  - Espera bbox VERDE estable (confianza > 85%)")
    print("\nCONTROLES:")
    print("  SPACE - Capturar")
    print("  ESC   - Cancelar")
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
            log("ERROR: Frame no leido")
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
            label = f"{confianza_actual:.0%}"
            cv2.putText(display, label, (x, y-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        else:
            contador_estable = 0
        
        # Status bar (en frame ORIGINAL antes de adaptar)
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
        
        # Adaptar para LCD vertical y mostrar
        display_lcd = adaptar_para_lcd(display)
        
        # Texto adicional en parte vertical
        cv2.putText(display_lcd, datos['nombre'][:20], 
                   (10, LCD_H - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow(WINDOW_NAME, display_lcd)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            log("Cancelado por usuario")
            break
        elif key == 32:  # SPACE
            if rostro_actual is not None and contador_estable >= 5:
                frame_capturado = frame.copy()
                rostro_capturado = rostro_actual
                log(f"Captura exitosa (confianza: {confianza_actual:.2%})")
                break
            else:
                log("WARN: Esperando deteccion estable...")
    
    cap.release()
    cv2.destroyAllWindows()
    
    return frame_capturado, rostro_capturado


def confirmar_captura(frame, rostro, datos):
    """Muestra captura y pide confirmacion."""
    x, y, w, h = rostro[:4].astype(int)
    confianza = float(rostro[-1])
    
    preview = frame.copy()
    cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 0), 2)
    cv2.putText(preview, "CAPTURA", (x, y-10),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    print("\n" + "=" * 50)
    print("  CAPTURA EXITOSA")
    print("=" * 50)
    print(f"  Nombre:    {datos['nombre']}")
    print(f"  Matricula: {datos['matricula']}")
    print(f"  Grupo:     {datos['grupo']}")
    print(f"  Confianza: {confianza:.2%}")
    print("=" * 50)
    
    # Adaptar y mostrar en LCD
    preview_lcd = adaptar_para_lcd(preview)
    cv2.putText(preview_lcd, datos['nombre'][:20], 
               (10, LCD_H - 50),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.putText(preview_lcd, f"{confianza:.0%}", 
               (10, LCD_H - 20),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    configurar_ventana()
    cv2.imshow(WINDOW_NAME, preview_lcd)
    cv2.waitKey(3000)
    cv2.destroyAllWindows()
    
    while True:
        respuesta = input("\nGuardar este alumno? (s/n): ").strip().lower()
        if respuesta in ('s', 'si', 'y', 'yes'):
            return True
        elif respuesta in ('n', 'no'):
            return False
        print("Responde 's' o 'n'")


def guardar_alumno(frame, rostro, datos, reconocedor):
    """Genera embedding y guarda en SQLite."""
    try:
        rostro_alineado = reconocedor.alignCrop(frame, rostro)
        embedding = reconocedor.feature(rostro_alineado)
        embedding_bytes = embedding.tobytes()
        
        log(f"Embedding generado: shape={embedding.shape}, "
            f"bytes={len(embedding_bytes)}")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alumnos (nombre, grupo, matricula, embedding, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (datos['nombre'], datos['grupo'], datos['matricula'], embedding_bytes))
        
        alumno_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        log(f"Alumno guardado en BD: ID={alumno_id}")
        return alumno_id
    except Exception as e:
        log(f"ERROR guardando: {e}")
        return None


def main():
    log("=" * 50)
    log("KEYON Enrolar Alumno v0.2.0")
    log("=" * 50)
    
    if not os.path.exists(DB_PATH):
        log(f"ERROR: BD no encontrada: {DB_PATH}")
        sys.exit(1)
    if not os.path.exists(MODELO_DET):
        log(f"ERROR: Modelo deteccion no encontrado: {MODELO_DET}")
        sys.exit(1)
    if not os.path.exists(MODELO_REC):
        log(f"ERROR: Modelo reconocimiento no encontrado: {MODELO_REC}")
        sys.exit(1)
    
    log("Cargando modelos AI...")
    detector = cv2.FaceDetectorYN.create(
        MODELO_DET, "", (CAMERA_W, CAMERA_H),
        score_threshold=0.6
    )
    reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")
    log("Modelos cargados")
    
    enrolados = 0
    while True:
        datos = pedir_datos()
        frame, rostro = capturar_rostro(detector, datos)
        
        if frame is None or rostro is None:
            print("\nCaptura cancelada")
        else:
            if confirmar_captura(frame, rostro, datos):
                alumno_id = guardar_alumno(frame, rostro, datos, reconocedor)
                if alumno_id:
                    print(f"\n  ALUMNO ENROLADO con ID={alumno_id}")
                    enrolados += 1
                else:
                    print("\n  ERROR al guardar")
            else:
                print("\n  Captura descartada")
        
        respuesta = input("\nEnrolar otro alumno? (s/n): ").strip().lower()
        if respuesta not in ('s', 'si', 'y', 'yes'):
            break
    
    print("\n" + "=" * 50)
    print(f"  Total enrolados en esta sesion: {enrolados}")
    print("=" * 50)
    log(f"Sesion finalizada. Total: {enrolados}")


if __name__ == "__main__":
    main()
