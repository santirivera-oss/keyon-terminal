import cv2
import sqlite3
import numpy as np
import sys

DB_PATH = "/home/keyon/keyon-terminal/db/keyon.db"
MODELO_DET = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
MODELO_REC = "/home/keyon/keyon-terminal/modelos/face_recognition_sface_2021dec.onnx"

UMBRAL_COSENO = 0.363
UMBRAL_L2 = 1.128

print("=" * 50)
print("  KEYON - Identificar Rostro")
print("=" * 50)

if len(sys.argv) < 2:
    print("Uso: python3 identificar.py <foto.jpg>")
    sys.exit(1)

foto_path = sys.argv[1]
imagen = cv2.imread(foto_path)
if imagen is None:
    print(f"ERROR: No pude cargar {foto_path}")
    sys.exit(1)

h, w = imagen.shape[:2]
print(f"Imagen: {w}x{h}")

detector = cv2.FaceDetectorYN.create(MODELO_DET, "", (w, h),
                                      score_threshold=0.6)
reconocedor = cv2.FaceRecognizerSF.create(MODELO_REC, "")

_, rostros = detector.detect(imagen)
if rostros is None or len(rostros) == 0:
    print("\nNo se detecto ningun rostro")
    sys.exit(1)

rostro = rostros[0]
confianza = rostro[-1]
print(f"Rostro detectado con confianza {confianza:.2%}")

rostro_alineado = reconocedor.alignCrop(imagen, rostro)
emb_nuevo = reconocedor.feature(rostro_alineado)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, nombre, grupo, matricula, embedding FROM alumnos WHERE activo=1")
alumnos = cursor.fetchall()
conn.close()

if not alumnos:
    print("\nNo hay alumnos en la BD")
    sys.exit(1)

print(f"\nComparando contra {len(alumnos)} alumnos registrados...\n")

mejor_match = None
mejor_score_coseno = 0.0
mejor_score_l2 = 999.0

for alumno in alumnos:
    alumno_id, nombre, grupo, matricula, emb_blob = alumno
    emb_guardado = np.frombuffer(emb_blob, dtype=np.float32).reshape(1, 128)

    score_c = reconocedor.match(emb_nuevo, emb_guardado, cv2.FaceRecognizerSF_FR_COSINE)
    score_l = reconocedor.match(emb_nuevo, emb_guardado, cv2.FaceRecognizerSF_FR_NORM_L2)

    icono = "✓" if (score_c > UMBRAL_COSENO and score_l < UMBRAL_L2) else "×"
    print(f"  {icono} {nombre} ({grupo}): cos={score_c:.4f} | L2={score_l:.4f}")

    if score_c > mejor_score_coseno:
        mejor_score_coseno = score_c
        mejor_score_l2 = score_l
        mejor_match = alumno

print(f"\n{'=' * 50}")
if mejor_match and mejor_score_coseno > UMBRAL_COSENO and mejor_score_l2 < UMBRAL_L2:
    alumno_id, nombre, grupo, matricula, _ = mejor_match
    print(f"  IDENTIFICADO: {nombre}")
    print(f"  Grupo: {grupo} | Matricula: {matricula}")
    print(f"  Scores: cos={mejor_score_coseno:.4f} | L2={mejor_score_l2:.4f}")
else:
    print(f"  NO RECONOCIDO")
    if mejor_match:
        nombre = mejor_match[1]
        print(f"  Mejor candidato: {nombre} (cos={mejor_score_coseno:.4f})")
        print(f"  Pero no supera umbrales minimos")
print(f"{'=' * 50}")
