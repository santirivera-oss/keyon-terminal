import cv2
import sys

print("=" * 50)
print("  KEYON Terminal Pro v2 - YuNet Detection")
print("=" * 50)

# Rutas
modelo_path = "/home/keyon/keyon-terminal/modelos/face_detection_yunet_2023mar.onnx"
imagen_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test2.jpg"

# Cargar imagen
imagen = cv2.imread(imagen_path)
if imagen is None:
    print(f"ERROR: No pude cargar {imagen_path}")
    sys.exit(1)

h, w = imagen.shape[:2]
print(f"Imagen: {w}x{h} pixels")

# Crear detector YuNet
detector = cv2.FaceDetectorYN.create(
    modelo_path,
    "",
    (w, h),
    score_threshold=0.6,   # 60% confianza minima
    nms_threshold=0.3,
    top_k=5000
)

print(f"YuNet cargado con umbral 0.6")

# Detectar
_, rostros = detector.detect(imagen)

if rostros is None:
    print("\n*** NINGUN ROSTRO DETECTADO ***")
    sys.exit(0)

print(f"\n*** ROSTROS DETECTADOS: {len(rostros)} ***\n")

# Dibujar resultados
for i, rostro in enumerate(rostros):
    # Coordenadas del bounding box
    x, y, w_f, h_f = rostro[:4].astype(int)
    confianza = rostro[-1]

    # Landmarks: ojo_izq, ojo_der, nariz, boca_izq, boca_der
    landmarks = rostro[4:14].astype(int).reshape(5, 2)

    # Dibujar rectangulo del rostro
    cv2.rectangle(imagen, (x, y), (x+w_f, y+h_f), (0, 255, 0), 3)

    # Dibujar texto con confianza
    texto = f"Rostro {i+1} ({confianza:.2f})"
    cv2.putText(imagen, texto, (x, y-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Dibujar landmarks (puntos rojos)
    colores_lm = [(255,0,0),(0,0,255),(0,255,255),(255,0,255),(255,255,0)]
    nombres_lm = ["ojoIzq","ojoDer","nariz","bocaIzq","bocaDer"]
    for j, (lx, ly) in enumerate(landmarks):
        cv2.circle(imagen, (lx, ly), 4, colores_lm[j], -1)

    print(f"  Rostro {i+1}:")
    print(f"    Box: ({x},{y}) {w_f}x{h_f}")
    print(f"    Confianza: {confianza:.2%}")
    print(f"    Landmarks: ojo_izq={tuple(landmarks[0])}, "
          f"nariz={tuple(landmarks[2])}, boca={tuple(landmarks[3])}")

# Guardar resultado
output_path = "/tmp/test2_yunet.jpg"
cv2.imwrite(output_path, imagen)
print(f"\nResultado guardado en: {output_path}")
print("=" * 50)

