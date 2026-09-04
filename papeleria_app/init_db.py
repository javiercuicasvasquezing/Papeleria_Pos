"""
init_db.py
----------
Script de conveniencia para crear/actualizar el esquema de la base de datos
SQLite (papeleria.db) a partir de los modelos definidos en models.py.

Uso:
    python init_db.py

Este script existe como archivo SEPARADO (en vez de meter el bloque
`if __name__ == "__main__":` dentro de database.py) para evitar un problema
clásico de Python: si database.py se ejecutara directamente, se cargaría bajo
el nombre de módulo "__main__", mientras que models.py importaría la base
declarativa como "database.Base". Eso crearía dos objetos `Base` distintos y
`create_all` no encontraría las tablas de los modelos.

Al importar `database` desde aquí (un script distinto), el módulo se carga
siempre con su nombre real "database", por lo que `models.py` y este script
comparten exactamente la misma instancia de `Base`.
"""

from database import init_db, SQLALCHEMY_DATABASE_URL

if __name__ == "__main__":
    init_db()
    print(f"Base de datos inicializada correctamente en: {SQLALCHEMY_DATABASE_URL}")
