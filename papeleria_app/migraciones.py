"""
migraciones.py
---------------
Migraciones de base de datos, pensadas para aplicarse sobre una base de
datos EXISTENTE sin perder datos ni romper nada. Cada migración:
    - Es IDEMPOTENTE: correrla varias veces no causa daño (si ya se aplicó,
      simplemente no hace nada la próxima vez).
    - Verifica primero si hace falta aplicarse (columna/tabla/valor
      existente) antes de tocar cualquier cosa.
    - Nunca borra la base de datos ni datos existentes.

Se ejecutan automáticamente al iniciar el backend (ver el evento
'startup' en main.py) y también desde crear_usuario.py -- así que en
condiciones normales NUNCA necesitas correr este archivo a mano. Aun así,
puedes hacerlo si quieres ver el detalle de qué se aplicó:
    python migraciones.py
"""

import sqlite3

from database import DB_PATH


def _tabla_existe(cursor: sqlite3.Cursor, tabla: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cursor.fetchone() is not None


def _columna_existe(cursor: sqlite3.Cursor, tabla: str, columna: str) -> bool:
    cursor.execute(f"PRAGMA table_info({tabla})")
    return any(fila[1] == columna for fila in cursor.fetchall())


# ---------------------------------------------------------------------------
# Migración: rol 'VENDEDOR' (nombre original) -> 'CAJERO' (nombre actual)
# ---------------------------------------------------------------------------
#
# El campo `rol` en SQLite se guarda como texto libre (VARCHAR), sin una
# restricción CHECK que limite los valores posibles -- por eso esta
# migración es simplemente un UPDATE de datos, sin necesidad de reconstruir
# la tabla completa.

def _migrar_rol_vendedor_a_cajero(cursor: sqlite3.Cursor) -> int:
    if not _tabla_existe(cursor, "usuarios"):
        return 0
    cursor.execute("UPDATE usuarios SET rol = 'CAJERO' WHERE rol = 'VENDEDOR'")
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Migración: columna 'categoria' (nombre original) -> 'marca' (nombre actual)
# en la tabla productos.
# ---------------------------------------------------------------------------
#
# A diferencia de la migración de roles (que era solo un UPDATE de datos),
# esta SÍ requiere cambiar la estructura de la tabla: la columna cambia de
# nombre. Usamos `ALTER TABLE ... RENAME COLUMN`, soportado por SQLite
# desde la versión 3.25 (2018) -- preserva todos los datos existentes, solo
# cambia la etiqueta de la columna.

def _migrar_categoria_a_marca(cursor: sqlite3.Cursor) -> bool:
    if not _tabla_existe(cursor, "productos"):
        return False
    if not _columna_existe(cursor, "productos", "categoria"):
        return False  # ya migrada (o instalación nueva, que ya nace con 'marca')
    cursor.execute("ALTER TABLE productos RENAME COLUMN categoria TO marca")
    return True


# ---------------------------------------------------------------------------
# Punto de entrada: aplica todas las migraciones, en orden
# ---------------------------------------------------------------------------

def _migrar_activo_productos(cursor: sqlite3.Cursor) -> bool:
    if not _tabla_existe(cursor, "productos"):
        return False
    if _columna_existe(cursor, "productos", "activo"):
        return False
    cursor.execute("ALTER TABLE productos ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")
    return True


def _migrar_quitar_check_yape_referencia(cursor: sqlite3.Cursor, conexion: sqlite3.Connection) -> bool:
    """
    Reconstruye la tabla 'ventas' sin la restricción vieja que exigía
    'referencia_pago' obligatorio para YAPE (esa regla ya no aplica: ahora
    el número de operación es opcional). SQLite no permite quitar una
    restricción CHECK directamente, así que se renombra la tabla, se crea
    de nuevo con el esquema actual (sin la restricción) y se copian todos
    los datos -- ninguna venta se pierde.
    """
    if not _tabla_existe(cursor, "ventas"):
        return False
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ventas'")
    fila = cursor.fetchone()
    if fila is None or "ck_venta_yape_requiere_referencia" not in (fila[0] or ""):
        return False  # ya migrada, o instalación nueva que ya nace sin la restricción

    cursor.execute("ALTER TABLE ventas RENAME TO ventas_old")

    # Al renombrar la tabla, sus índices (ej. ix_ventas_fecha) mantienen su
    # nombre original y quedarían "atados" a ventas_old -- si no se
    # eliminan antes, create_all() choca al intentar crear un índice con
    # ese mismo nombre para la tabla 'ventas' nueva.
    indices_viejos = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='ventas_old' "
        "AND name NOT LIKE 'sqlite_autoindex%'"
    ).fetchall()
    for (nombre_indice,) in indices_viejos:
        cursor.execute(f"DROP INDEX {nombre_indice}")

    conexion.commit()

    from database import engine
    import models
    models.Base.metadata.create_all(bind=engine, tables=[models.Venta.__table__])

    columnas = [c[1] for c in cursor.execute("PRAGMA table_info(ventas_old)").fetchall()]
    columnas_str = ", ".join(columnas)
    cursor.execute(f"INSERT INTO ventas ({columnas_str}) SELECT {columnas_str} FROM ventas_old")
    cursor.execute("DROP TABLE ventas_old")
    return True


def ejecutar_migraciones() -> None:
    """
    Aplica todas las migraciones pendientes sobre papeleria.db. Si el
    archivo de base de datos todavía no existe (instalación nueva), no hay
    nada que migrar -- `init_db()` se encargará de crear las tablas ya con
    la estructura correcta desde cero.
    """
    if not DB_PATH.exists():
        return

    conexion = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conexion.cursor()

        usuarios_migrados = _migrar_rol_vendedor_a_cajero(cursor)
        columna_marca_migrada = _migrar_categoria_a_marca(cursor)
        columna_activo_migrada = _migrar_activo_productos(cursor)
        yape_migrado = _migrar_quitar_check_yape_referencia(cursor, conexion)

        conexion.commit()

        if yape_migrado:
            print("[migraciones] Tabla 'ventas' actualizada: Yape ya no exige número de operación.")

        if usuarios_migrados:
            print(
                f"[migraciones] {usuarios_migrados} usuario(s) actualizado(s): "
                "rol 'VENDEDOR' -> 'CAJERO'."
            )
        if columna_marca_migrada:
            print("[migraciones] Columna 'categoria' renombrada a 'marca' en productos.")
        if columna_activo_migrada:
            print("[migraciones] Columna 'activo' agregada a productos.")
    finally:
        conexion.close()


if __name__ == "__main__":
    ejecutar_migraciones()
    print("Migraciones aplicadas correctamente (o no había nada pendiente).")
