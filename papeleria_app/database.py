"""
database.py
------------
Configuración central de la base de datos para el Sistema POS de Librería/Papelería.

Responsabilidades de este módulo:
    - Crear el engine de SQLAlchemy apuntando a un archivo SQLite local (papeleria.db).
    - Exponer `SessionLocal` para crear sesiones de base de datos por request.
    - Exponer `Base`, la clase declarativa de la que heredarán todos los modelos ORM.
    - Exponer `get_db`, una dependencia de FastAPI que entrega una sesión y garantiza
      su cierre correcto incluso si ocurre una excepción.

Notas de diseño:
    - `check_same_thread=False` es obligatorio para SQLite cuando la app se sirve con
      Uvicorn/FastAPI, ya que cada request puede ser atendido en un hilo distinto.
    - Se habilita el pragma `foreign_keys=ON` en cada conexión, porque SQLite NO aplica
      llaves foráneas por defecto. Esto es crítico para la integridad referencial entre
      ventas -> detalle_ventas -> productos/clientes.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------------------------------------------------------------------------
# Configuración de la base de datos
# ---------------------------------------------------------------------------

# Ubicación del archivo papeleria.db. Deliberadamente NO se usa una ruta
# relativa simple ("./papeleria.db"), porque el directorio de trabajo actual
# ("current working directory") cambia según cómo se lance la app:
#   - En desarrollo: depende de desde dónde corras `uvicorn` o `python`.
#   - Empaquetado como .exe con PyInstaller (--onefile): el .exe se
#     autoextrae a una carpeta temporal en tiempo de ejecución, así que una
#     ruta relativa terminaría creando (o buscando) la base de datos DENTRO
#     de esa carpeta temporal, que se borra al cerrar el programa.
#
# En vez de eso, calculamos la carpeta donde vive el propio ejecutable
# (o este archivo .py, en desarrollo) y colocamos papeleria.db siempre AHÍ,
# sin importar desde dónde se haya lanzado el programa.
if getattr(sys, "frozen", False):
    # La app corre empaquetada (PyInstaller). sys.executable apunta al .exe.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    # La app corre como script .py normal (desarrollo).
    BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "papeleria.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# El engine es el punto de entrada de bajo nivel a la base de datos.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # Necesario únicamente para SQLite + FastAPI (multi-hilo).
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Se ejecuta cada vez que se abre una nueva conexión física a SQLite.
    Activa la verificación de llaves foráneas, que SQLite trae desactivada
    por defecto (a diferencia de PostgreSQL/MySQL).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Fábrica de sesiones. Cada request de FastAPI usará una instancia independiente.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa. Todos los modelos (Producto, Cliente, Venta, DetalleVenta)
# heredarán de esta clase para ser reconocidos por el ORM.
Base = declarative_base()


def get_db():
    """
    Dependencia de FastAPI para inyectar una sesión de base de datos en cada endpoint.

    Uso típico en un router:
        @router.get("/productos/")
        def listar_productos(db: Session = Depends(get_db)):
            ...

    El patrón try/finally garantiza que la sesión se cierre siempre,
    liberando la conexión al pool aunque el endpoint lance una excepción.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Crea todas las tablas definidas en los modelos (si no existen todavía).
    Se debe llamar una vez al iniciar la aplicación (por ejemplo, en el
    evento 'startup' de FastAPI o al ejecutar `python database.py`).

    En un entorno de producción más avanzado esto se reemplazaría por
    migraciones con Alembic, pero para una app de escritorio local con
    SQLite, `create_all` es suficiente y evita complejidad innecesaria.
    """
    # Se importa aquí (import tardío) para evitar importaciones circulares
    # entre database.py y models.py.
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)


# NOTA IMPORTANTE:
# Deliberadamente NO se incluye aquí un bloque `if __name__ == "__main__":` que
# llame a init_db(). Si este archivo se ejecutara directamente como script
# (`python database.py`), Python lo cargaría bajo el nombre de módulo "__main__",
# mientras que models.py seguiría haciendo `from database import Base` usando el
# nombre "database". Esto generaría DOS instancias distintas de `Base` (una por
# cada nombre de módulo) y, por lo tanto, `Base.metadata` quedaría vacío al
# ejecutar `create_all`, creando un archivo .db sin tablas.
#
# Para inicializar la base de datos usa el script independiente `init_db.py`
# (que importa este módulo por su nombre real "database"), o deja que
# `init_db()` se invoque desde el evento de startup de FastAPI en main.py.
