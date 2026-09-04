# PapeleriaPOS.spec
#
# Configuración de PyInstaller para empaquetar la app principal (backend +
# interfaz de escritorio, todo en un solo .exe con ventana, sin consola).
#
# Uso (desde la carpeta papeleria_app, en Windows, con el entorno virtual
# activado donde instalaste las dependencias):
#     pyinstaller PapeleriaPOS.spec
#
# El resultado queda en dist/PapeleriaPOS.exe
#
# NOTA: este archivo ya incluye todo lo que se determinó necesario durante
# las pruebas de empaquetado (ver INSTRUCCIONES_EXE.md):
#   - `pathex=['desktop']`: para que PyInstaller encuentre los módulos de
#     la interfaz (app.py, api_client.py, views/), que se importan de forma
#     dinámica desde launcher.py y no son detectables por análisis estático.
#   - `hiddenimports`: los módulos de la interfaz (arriba) + submódulos de
#     uvicorn que se cargan dinámicamente (loops, protocolos, lifespan) y
#     que PyInstaller no sigue automáticamente.
#   - `collect_data_files('customtkinter')`: para incluir los temas (.json)
#     y fuentes (.ttf/.otf) que CustomTkinter necesita en tiempo de
#     ejecución -- sin esto, la app abriría con la tipografía y el tema
#     rotos (o ni siquiera abriría).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('customtkinter')

hiddenimports = (
    ['app', 'api_client']
    + collect_submodules('views')
    + [
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ]
)

a = Analysis(
    ['launcher.py'],
    pathex=['desktop'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PapeleriaPOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # sin ventana de consola negra detrás (app con GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,            # si tienes un .ico propio, pon aquí la ruta
)
