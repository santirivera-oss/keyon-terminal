import sqlite3
import os

DB_PATH = "/home/keyon/keyon-terminal/db/keyon.db"

print("=" * 50)
print("  KEYON Terminal Pro v2 - Init DB")
print("=" * 50)

# Si ya existe, preguntamos
if os.path.exists(DB_PATH):
    respuesta = input(f"La BD ya existe en {DB_PATH}\n¿Borrar y recrear? (s/N): ")
    if respuesta.lower() != 's':
        print("Cancelado.")
        exit(0)
    os.remove(DB_PATH)
    print("BD anterior eliminada")

# Crear conexion
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Tabla de alumnos
cursor.execute("""
CREATE TABLE alumnos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    grupo TEXT,
    matricula TEXT UNIQUE,
    embedding BLOB NOT NULL,
    fecha_registro TEXT DEFAULT (datetime('now', 'localtime')),
    activo INTEGER DEFAULT 1
)
""")
print("Tabla 'alumnos' creada")

# Tabla de asistencias (log local antes de sync a Firebase)
cursor.execute("""
CREATE TABLE asistencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id INTEGER NOT NULL,
    timestamp TEXT DEFAULT (datetime('now', 'localtime')),
    tipo TEXT DEFAULT 'entrada',
    score_cosine REAL,
    score_l2 REAL,
    sincronizado_firebase INTEGER DEFAULT 0,
    FOREIGN KEY (alumno_id) REFERENCES alumnos (id)
)
""")
print("Tabla 'asistencias' creada")

# Indices para velocidad
cursor.execute("CREATE INDEX idx_asistencias_timestamp ON asistencias(timestamp)")
cursor.execute("CREATE INDEX idx_asistencias_sync ON asistencias(sincronizado_firebase)")
cursor.execute("CREATE INDEX idx_alumnos_matricula ON alumnos(matricula)")
print("Indices creados")

conn.commit()
conn.close()

print(f"\nBD lista: {DB_PATH}")
print("=" * 50)
