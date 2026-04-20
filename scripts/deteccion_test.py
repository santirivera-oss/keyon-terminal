import cv2
import sys

print("=" * 50)
print("  KEYON Terminal Pro v2 - Prueba Detección")
print("=" * 50)

# Cargar imagen
imagen_path = "/tmp/test2.jpg"
imagen = cv2.imread(imagen_path)

if imagen is None:
    print(f"ERROR: No pude cargar {imagen_path}")
    sys.exit(1)

print(f"Imagen cargada: {imagen.shape[1]}x{imagen.shape[0]} pixels")

# Cargar detector Haar Cascade (viene con OpenCV)
cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
detector = cv2.CascadeClassifier(cascade_path)
print(f"Detector cargado: {cascade_path}")

# Convertir a escala de grises (Haar Cascades requiere gris)
gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

# Detectar rostros
rostros = detector.detectMultiScale(
    gris,
    scaleFactor=1.1,
    minNeighbors=5,
    minSize=(30, 30)
)

print(f"\n*** ROSTROS DETECTADOS: {len(rostros)} ***")

# Dibujar rectangulos verdes alrededor de cada rostro
for i, (x, y, w, h) in enumerate(rostros):
    cv2.rectangle(imagen, (x, y), (x+w, y+h), (0, 255, 0), 3)
    cv2.putText(imagen, f"Rostro {i+1}", (x, y-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    print(f"  Rostro {i+1}: posicion ({x},{y}) tamaño {w}x{h}")

# Guardar resultado
output_path = "/tmp/test2_detected.jpg"
cv2.imwrite(output_path, imagen)
print(f"\nResultado guardado en: {output_path}")
print("=" * 50)
