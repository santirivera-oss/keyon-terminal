import cv2
import numpy as np
import sys

print("=" * 50)
print("  KEYON Terminal Pro v2 - SFace Recognition")
print("=" * 50)

# Rutas
modelo_det = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
modelo_rec = "/home/keyon/keyon-terminal/modelos/face_recognition_sface_2021dec.onnx"

# Argumentos: 2 imagenes a comparar
if len(sys.argv) < 3:
    print("Uso: python3 reconocer_sface.py <imagen1> <imagen2>")
    print("Ejemplo: python3 reconocer_sface.py /tmp/foto1.jpg /tmp/foto2.jpg")
    sys.exit(1)

img1_path = sys.argv[1]
img2_path = sys.argv[2]

# Cargar imagenes
img1 = cv2.imread(img1_path)
img2 = cv2.imread(img2_path)

if img1 is None or img2 is None:
    print(f"ERROR: No pude cargar imagenes")
    sys.exit(1)

print(f"Imagen 1: {img1_path}")
print(f"Imagen 2: {img2_path}")

# Inicializar detector (YuNet) y reconocedor (SFace)
detector = cv2.FaceDetectorYN.create(modelo_det, "", (320, 320),
                                      score_threshold=0.6)
reconocedor = cv2.FaceRecognizerSF.create(modelo_rec, "")

def obtener_embedding(imagen, etiqueta):
    """Detecta rostro, alinea y extrae embedding 128-dim"""
    h, w = imagen.shape[:2]
    detector.setInputSize((w, h))
    _, rostros = detector.detect(imagen)

    if rostros is None or len(rostros) == 0:
        print(f"  [{etiqueta}] No se detecto ningun rostro")
        return None

    # Tomar el rostro de mayor confianza
    rostro_mas_confiable = rostros[0]
    confianza = rostro_mas_confiable[-1]
    print(f"  [{etiqueta}] Rostro detectado con confianza {confianza:.2%}")

    # Alinear y extraer embedding
    rostro_alineado = reconocedor.alignCrop(imagen, rostro_mas_confiable)
    embedding = reconocedor.feature(rostro_alineado)

    return embedding

# Extraer embeddings
print("\n--- Procesando imagenes ---")
emb1 = obtener_embedding(img1, "Imagen 1")
emb2 = obtener_embedding(img2, "Imagen 2")

if emb1 is None or emb2 is None:
    print("\nFalta rostro en alguna imagen, no se puede comparar")
    sys.exit(1)

# Comparar embeddings
# Coseno: mas alto = mas similar (0 a 1)
# L2: mas bajo = mas similar
score_coseno = reconocedor.match(emb1, emb2, cv2.FaceRecognizerSF_FR_COSINE)
score_l2 = reconocedor.match(emb1, emb2, cv2.FaceRecognizerSF_FR_NORM_L2)

# Umbrales recomendados por OpenCV
UMBRAL_COSENO = 0.363  # mayor = misma persona
UMBRAL_L2 = 1.128       # menor = misma persona

print(f"\n--- Resultados comparacion ---")
print(f"Score coseno: {score_coseno:.4f}  (umbral: >{UMBRAL_COSENO})")
print(f"Score L2:     {score_l2:.4f}  (umbral: <{UMBRAL_L2})")

# Veredicto
es_misma_persona = score_coseno > UMBRAL_COSENO and score_l2 < UMBRAL_L2

print(f"\n{'=' * 50}")
if es_misma_persona:
    print(f"  VEREDICTO: MISMA PERSONA (match)")
else:
    print(f"  VEREDICTO: PERSONAS DIFERENTES (no match)")
print(f"{'=' * 50}")
