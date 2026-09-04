import sqlite3
import shutil
import os

DB = r"papeleria (1).db"
BACKUP = r"papeleria_BACKUP_ANTES_REPARACION.db"

print("Base de datos:", os.path.abspath(DB))

# ============================================================
# 1. Verificar que existe
# ============================================================

if not os.path.exists(DB):
    print("ERROR: No se encontró la base de datos.")
    raise SystemExit(1)

# ============================================================
# 2. Crear respaldo
# ============================================================

if not os.path.exists(BACKUP):
    shutil.copy2(DB, BACKUP)
    print("Respaldo creado:", BACKUP)
else:
    print("El respaldo ya existe:", BACKUP)

# ============================================================
# 3. Conectar
# ============================================================

conn = sqlite3.connect(DB)
cursor = conn.cursor()

try:
    # Desactivar temporalmente las FK
    cursor.execute("PRAGMA foreign_keys = OFF")

    # --------------------------------------------------------
    # Comprobar datos actuales
    # --------------------------------------------------------

    cursor.execute("SELECT COUNT(*) FROM detalle_ventas")
    cantidad_detalles = cursor.fetchone()[0]

    print("Detalles de venta existentes:", cantidad_detalles)

    # --------------------------------------------------------
    # Crear tabla nueva
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE detalle_ventas_nueva (
            id INTEGER NOT NULL,
            venta_id INTEGER NOT NULL,
            producto_id INTEGER NOT NULL,
            tipo_venta VARCHAR(6) NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario_aplicado NUMERIC(10, 2) NOT NULL,
            subtotal NUMERIC(10, 2) NOT NULL,

            PRIMARY KEY (id),

            CONSTRAINT ck_detalle_cantidad_positiva
                CHECK (cantidad > 0),

            CONSTRAINT ck_detalle_precio_no_negativo
                CHECK (precio_unitario_aplicado >= 0),

            CONSTRAINT ck_detalle_subtotal_no_negativo
                CHECK (subtotal >= 0),

            FOREIGN KEY(venta_id)
                REFERENCES ventas (id),

            FOREIGN KEY(producto_id)
                REFERENCES productos (id)
        )
    """)

    # --------------------------------------------------------
    # Copiar todos los datos
    # --------------------------------------------------------

    cursor.execute("""
        INSERT INTO detalle_ventas_nueva (
            id,
            venta_id,
            producto_id,
            tipo_venta,
            cantidad,
            precio_unitario_aplicado,
            subtotal
        )
        SELECT
            id,
            venta_id,
            producto_id,
            tipo_venta,
            cantidad,
            precio_unitario_aplicado,
            subtotal
        FROM detalle_ventas
    """)

    # --------------------------------------------------------
    # Eliminar tabla defectuosa
    # --------------------------------------------------------

    cursor.execute("DROP TABLE detalle_ventas")

    # --------------------------------------------------------
    # Renombrar tabla nueva
    # --------------------------------------------------------

    cursor.execute("""
        ALTER TABLE detalle_ventas_nueva
        RENAME TO detalle_ventas
    """)

    conn.commit()

    # --------------------------------------------------------
    # Volver a activar FK
    # --------------------------------------------------------

    cursor.execute("PRAGMA foreign_keys = ON")

    print()
    print("========================================")
    print("BASE DE DATOS REPARADA CORRECTAMENTE")
    print("========================================")

except Exception as e:

    conn.rollback()

    print()
    print("========================================")
    print("ERROR DURANTE LA REPARACIÓN")
    print("========================================")
    print(e)
    print()
    print("La base original NO debe eliminarse.")
    print("Puedes restaurarla usando:")
    print(BACKUP)

    conn.close()
    raise SystemExit(1)

# ============================================================
# 4. Verificaciones
# ============================================================

print()
print("=== FOREIGN KEYS DESPUÉS DE LA REPARACIÓN ===")

cursor.execute("PRAGMA foreign_key_list(detalle_ventas)")

for fila in cursor.fetchall():
    print(fila)

print()
print("=== CANTIDAD DE DETALLES ===")

cursor.execute("SELECT COUNT(*) FROM detalle_ventas")

print(cursor.fetchone()[0])

print()
print("=== TABLAS ===")

cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""")

for tabla in cursor.fetchall():
    print(tabla[0])

conn.close()

print()
print("Proceso terminado.")