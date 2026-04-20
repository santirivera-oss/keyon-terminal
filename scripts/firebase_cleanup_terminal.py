#!/usr/bin/env python3
"""
Limpia registros de prueba escritos por Terminal Pi.

Uso:
    python3 firebase_cleanup_terminal.py              # solo lista, no borra
    python3 firebase_cleanup_terminal.py --delete     # borra confirmando
    python3 firebase_cleanup_terminal.py --delete -y  # borra sin preguntar
"""

import firebase_admin
from firebase_admin import credentials, firestore
import sys

CRED = "/home/keyon/keyon-terminal/firebase-credentials.json"
COLECCION = "ingresos_cbtis"
FILTRO_ORIGEN = "terminal_pi"

DELETE_MODE = "--delete" in sys.argv
SKIP_CONFIRM = "-y" in sys.argv

print("=" * 60)
print(f"  Firebase Cleanup - Terminal Pi Test Records")
print("=" * 60)

cred = credentials.Certificate(CRED)
firebase_admin.initialize_app(cred)
db = firestore.client()
print(f"  Proyecto: {db.project}")
print(f"  Coleccion: {COLECCION}")
print(f"  Filtro: origen == '{FILTRO_ORIGEN}'")
print(f"  Modo: {'BORRAR' if DELETE_MODE else 'SOLO LISTAR'}")
print()

# Buscar todos los docs con origen = terminal_pi
query = db.collection(COLECCION).where("origen", "==", FILTRO_ORIGEN)
docs = list(query.stream())

if not docs:
    print("  No se encontraron registros de terminal_pi")
    print("  (Firebase esta limpio)")
    sys.exit(0)

print(f"  Encontrados {len(docs)} documentos:\n")

for i, doc in enumerate(docs, 1):
    data = doc.to_dict()
    print(f"  [{i}] ID: {doc.id}")
    print(f"      Identificador: {data.get('identificador', '?')}")
    print(f"      Nombre:        {data.get('nombre', '?')}")
    print(f"      Fecha/Hora:    {data.get('fecha', '?')} {data.get('hora', '?')}")
    print(f"      Terminal:      {data.get('terminalId', '?')}")
    print(f"      Score cos:     {data.get('scoreCosine', '?')}")
    print()

if not DELETE_MODE:
    print("  Para borrar estos documentos ejecuta:")
    print("    python3 firebase_cleanup_terminal.py --delete")
    sys.exit(0)

# Confirmar antes de borrar
if not SKIP_CONFIRM:
    resp = input(f"  ⚠ BORRAR estos {len(docs)} documentos? (escribe 'si'): ")
    if resp.strip().lower() != "si":
        print("  Cancelado. Nada borrado.")
        sys.exit(0)

# Borrar
print("\n  Borrando...")
borrados = 0
for doc in docs:
    try:
        doc.reference.delete()
        borrados += 1
        print(f"    ✓ Borrado: {doc.id}")
    except Exception as e:
        print(f"    × Error: {doc.id} - {e}")

print(f"\n  Total borrados: {borrados} de {len(docs)}")
print("=" * 60)
