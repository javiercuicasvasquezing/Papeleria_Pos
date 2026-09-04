"""
launcher.py
-----------
Punto de entrada ÚNICO para la app empaquetada como .exe: arranca el
backend (FastAPI/uvicorn) en un hilo en segundo plano, espera a que esté
listo, y luego abre la interfaz de escritorio -- todo en un solo proceso,
sin que el usuario final tenga que abrir dos terminales.

En desarrollo puedes seguir usando el flujo de dos terminales (uvicorn +
python desktop/app.py) si prefieres verlos por separado con sus propios
logs; este launcher es la forma "de producción" de correr todo junto, y es
el que se empaqueta como .exe (ver INSTRUCCIONES_EXE.md).

Uso manual (sin empaquetar):
    python launcher.py
"""

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# PARCHE NECESARIO para el .exe empaquetado SIN consola (--windowed):
# En ese modo, Windows no le asigna al proceso una consola real, así que
# `sys.stdout` y `sys.stderr` quedan como `None` (no simplemente "vacíos":
# son literalmente `None`). Varias librerías -- entre ellas el sistema de
# logging de uvicorn -- asumen que siempre existe un stream de salida válido
# y llaman cosas como `sys.stdout.isatty()`, lo que revienta con:
#     AttributeError: 'NoneType' object has no attribute 'isatty'
# Lo resolvemos reemplazando stdout/stderr por un "sumidero" (no hace nada,
# pero es un objeto válido con los métodos esperados) ANTES de importar
# cualquier librería que los use. Esto debe ir al principio del todo, antes
# incluso de `import uvicorn`.
# ---------------------------------------------------------------------------
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import uvicorn  # noqa: E402  (después del parche de stdout/stderr, a propósito)

# Aseguramos que tanto el backend (esta misma carpeta) como el frontend
# (subcarpeta desktop/) estén en el sys.path, sin importar desde dónde se
# haya lanzado este script ni cómo lo empaquete PyInstaller.
RAIZ = Path(__file__).resolve().parent
DESKTOP_DIR = RAIZ / "desktop"
for _ruta in (RAIZ, DESKTOP_DIR):
    _ruta_str = str(_ruta)
    if _ruta_str not in sys.path:
        sys.path.insert(0, _ruta_str)

HOST = "127.0.0.1"
PORT = 8000


def _iniciar_backend_en_hilo() -> uvicorn.Server:
    """
    Arranca uvicorn en un hilo daemon (muere automáticamente cuando cierra
    la ventana principal, sin dejar procesos huérfanos).

    `install_signal_handlers = lambda: None` es necesario porque uvicorn,
    por defecto, instala manejadores de señales (Ctrl+C, etc.) asumiendo
    que corre en el hilo principal del proceso -- aquí corre en un hilo
    secundario, así que los deshabilitamos explícitamente.

    `log_config=None` desactiva el sistema de logging "bonito" (con colores)
    de uvicorn, que es el que intenta inspeccionar stdout/stderr y es la
    causa raíz del error descrito arriba. En una app sin consola no hay
    ninguna ventana donde mostrar esos colores de todas formas, así que no
    perdemos nada al desactivarlo -- seguimos usando el logging estándar
    de Python por debajo.
    """
    from main import app as fastapi_app  # el objeto FastAPI del backend

    config = uvicorn.Config(
        fastapi_app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    servidor = uvicorn.Server(config)
    servidor.install_signal_handlers = lambda: None

    hilo = threading.Thread(target=servidor.run, daemon=True, name="backend-uvicorn")
    hilo.start()
    return servidor


def _esperar_backend_listo(timeout_segundos: float = 10.0) -> bool:
    """Sondea GET / hasta que el backend responda, o hasta agotar el tiempo."""
    limite = time.time() + timeout_segundos
    while time.time() < limite:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.2)
    return False


def main():
    _iniciar_backend_en_hilo()
    servidor_listo = _esperar_backend_listo()

    # Si el backend tardó más de lo esperado en arrancar, igual abrimos la
    # interfaz: el indicador de conexión de la pantalla de Inicio (🟢/🔴)
    # y la pantalla de login le avisarán al usuario que algo salió mal, en
    # vez de que el programa truene sin ninguna explicación.
    if not servidor_listo:
        print("Aviso: el backend no respondió a tiempo; la app se abrirá de todas formas.")

    from app import RootApp  # el RootApp de desktop/app.py

    ventana = RootApp()
    ventana.mainloop()


if __name__ == "__main__":
    main()
