import firebase_admin
from firebase_admin import credentials, firestore
import sys

CRED_PATH = "/home/keyon/keyon-terminal/firebase-credentials.json"

print("=" * 50)
print("  KEYON - Firebase Connection Test")
print("=" * 50)

# Inicializar Firebase
try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred)
    print("Firebase inicializado OK")
except Exception as e:
    print(f"ERROR al inicializar: {e}")
    sys.exit(1)

# Cliente Firestore
try:
    db = firestore.client()
    print(f"Firestore client conectado")
    print(f"Proyecto: {db.project}")
except Exception as e:
    print(f"ERROR al conectar Firestore: {e}")
    sys.exit(1)

# Listar colecciones raiz
print("\n--- Colecciones en tu Firestore ---")
try:
    colecciones = db.collections()
    count = 0
    for col in colecciones:
        print(f"  * {col.id}")
        count += 1
    print(f"\nTotal colecciones: {count}")
except Exception as e:
    print(f"ERROR al listar: {e}")
    sys.exit(1)

# Contar alumnos si existe esa coleccion
print("\n--- Conteo de alumnos ---")
try:
    alumnos_ref = db.collection("alumnos")
    docs = list(alumnos_ref.limit(5).stream())
    total = len(docs)
    print(f"Muestra de alumnos (primeros 5 o todos):")
    for doc in docs:
        data = doc.to_dict()
        nombre = data.get("nombre", "sin nombre")
        grupo = data.get("grupo", "sin grupo")
        print(f"  - ID: {doc.id} | {nombre} ({grupo})")

    # Intentar contar todos
    all_docs = alumnos_ref.stream()
    count_total = sum(1 for _ in all_docs)
    print(f"\nTotal alumnos en Firestore: {count_total}")
except Exception as e:
    print(f"ERROR al leer alumnos: {e}")

print("\n" + "=" * 50)
print("  Test completado")
print("=" * 50)
