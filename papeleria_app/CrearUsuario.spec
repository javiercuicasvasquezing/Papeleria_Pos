# CrearUsuario.spec
#
# Configuración de PyInstaller para el ejecutable de consola que crea
# usuarios (necesario para el primer arranque: crea el administrador antes
# de poder iniciar sesión en PapeleriaPOS.exe).
#
# Uso:
#     pyinstaller CrearUsuario.spec
#
# El resultado queda en dist/CrearUsuario.exe

a = Analysis(
    ['crear_usuario.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='CrearUsuario',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # SÍ necesita consola: es un programa interactivo de texto
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
