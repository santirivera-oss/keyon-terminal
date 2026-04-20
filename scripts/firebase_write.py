import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import sys

CRED_PATH = "/home/keyon/keyon-terminal/firebase-credentials.json"

print("=" * 50)
print("  KEYON - Firebase Write Test")
print("=" * 50)

# Inicializar
try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print(f"Conectado a: {db.project}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# Datos de prueba (simulación de una asistencia)
asistencia = {
    "alumnoId": "AT2099",
    "nombre": "Santiago Rivera (Test Terminal)",
    "grupo": "4BV",
    "tipo": "entrada",
    "timestamp": firestore.SERVER_TIMESTAMP,
    "timestampLocal": datetime.now().isoformat(),
    "metodoVerificacion": "facial_local_terminal",
    "scoreCosine": 0.7260,
    "scoreL2": 0.7403,
    "terminalId": "keyon-pi-zero2w-01",
    "dispositivo": "Raspberry Pi Zero 2W",
    "procesadoEnDispositivo": True,
    "sincronizadoFirebase": True,
    "version": "2.0.0-dev"
}

print("\nDatos a escribir:")
for key, value in asistencia.items():
    if key != "timestamp":
        print(f"  {key}: {value}")

# Escribir a coleccion nueva: asistencias_terminal
try:
    doc_ref = db.collection("asistencias_terminal").document()
    doc_ref.set(asistencia)
    print(f"\nDocumento escrito con ID: {doc_ref.id}")
    print(f"Coleccion: asistencias_terminal")
except Exception as e:
    print(f"\nERROR al escribir: {e}")
    sys.exit(1)

# Leer inmediatamente para confirmar
try:
    doc_leido = doc_ref.get()
    if doc_leido.exists:
        data = doc_leido.to_dict()
        print(f"\nVerificacion: documento existe en Firestore")
        print(f"  Alumno: {data['nombre']}")
        print(f"  Score coseno: {data['scoreCosine']}")
        print(f"  Timestamp server: {data['timestamp']}")
except Exception as e:
    print(f"ERROR al verificar: {e}")

print("\n" + "=" * 50)
print("  Test de escritura exitoso")
print("=" * 50)
