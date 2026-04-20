import cv2
import sqlite3
import numpy as np
import sys
import os

DB_PATH = "/home/keyon/keyon-terminal/db/keyon.db"
MODELO_DET = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = "/home/keyon/keyon-terminal/modelos/face_recognition_sface_2021dec.onnx"

print("=" * 50)
print("  KEYON - Registrar Alumno")
print("=" * 50)

# Argumentos
if len(sys.argv) < 4:
    print("Uso: python3 registrar.py <foto.jpg> <nombre> <grupo> [matricula]")
    print("Ejemplo: python3 registrar.py /tmp/foto1.jpg 'Santiago Rivera' '4BV' 'AT001'")
    sys.exit(1)

foto_path = sys.argv[1]
nombre = sys.argv[2]
grupo = sys.argv[3]
matricula = sys.argv[4] if len(sys.argv) > 4 else None

# Cargar imagen
imagen = cv2.imread(foto_path)
if imagen is None:
    print(f"ERROR: No pude cargar {foto_path}")
    sys.exit(1)

h, w = imagen.shape[:2]
print(f"Imagen: {w}x{h}")
print(f"Registrando: {nombre} | Grupo: {grupo}")

# Cargar detector y reconocedor
detector = cv2.FaceDetectorYN.create(MODELO_DET, "", (w, h),
                                      score_threshold=0.6)
reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")

# Detectar rostro
_, rostros = detector.detect(imagen)
if rostros is None or len(rostros) == 0:
    print("\nERROR: No se detecto ningun rostro en la foto")
    sys.exit(1)

if len(rostros) > 1:
    print(f"\nADVERTENCIA: Se detectaron {len(rostros)} rostros")
    print("Se usara el de mayor confianza")

# Tomar el rostro más confiable
rostro = rostros[0]
confianza = rostro[-1]
print(f"Rostro detectado con confianza: {confianza:.2%}")

if confianza < 0.85:
    print(f"\nADVERTENCIA: Confianza baja ({confianza:.2%})")
    respuesta = input("¿Continuar con esta foto? (s/N): ")
    if respuesta.lower() != 's':
        print("Cancelado. Intenta con mejor iluminacion o posicion.")
        sys.exit(0)

# Alinear + generar embedding 128-dim
rostro_alineado = reconocedor.alignCrop(imagen, rostro)
embedding = reconocedor.feature(rostro_alineado)

# embedding es array (1, 128) - lo guardamos como blob
embedding_bytes = embedding.tobytes()
print(f"Embedding generado: {embedding.shape}, {len(embedding_bytes)} bytes")

# Guardar en BD
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    cursor.execute("""
    INSERT INTO alumnos (nombre, grupo, matricula, embedding)
    VALUES (?, ?, ?, ?)
    """, (nombre, grupo, matricula, embedding_bytes))
    
    alumno_id = cursor.lastrowid
    conn.commit()
    print(f"\nAlumno registrado con ID: {alumno_id}")
    print(f"Confianza de detección: {confianza:.2%}")
except sqlite3.IntegrityError as e:
    print(f"\nERROR: Matricula '{matricula}' ya existe en BD")
    print(f"Detalle: {e}")
finally:
    conn.close()

print("=" * 50)
