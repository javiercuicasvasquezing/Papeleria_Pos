"""
security.py
------------
Utilidades de seguridad para el Sistema POS: hashing de contraseñas y
manejo de sesiones (tokens de acceso).

DECISIONES DE DISEÑO:

1. Hashing de contraseñas con PBKDF2-HMAC-SHA256 (librería estándar
   `hashlib`, sin dependencias externas como bcrypt/passlib). Es deliberado:
   evita depender de librerías con extensiones compiladas en C, que a veces
   dan problemas al empaquetar la app como .exe con PyInstaller. Con una sal
   aleatoria por usuario y 260,000 iteraciones, es un esquema robusto y
   ampliamente recomendado (OWASP) para este tipo de aplicación.

2. Sesiones en memoria (no en base de datos): al iniciar sesión se genera un
   token opaco (aleatorio, imposible de adivinar) que el cliente de
   escritorio debe enviar en cada request (`Authorization: Bearer <token>`).
   Los tokens expiran tras un tiempo de inactividad y se renuevan con cada
   uso (sliding session).

   Tradeoff a tener en cuenta: como las sesiones viven en memoria, si el
   backend se reinicia, todos los usuarios quedan desconectados (deben
   volver a iniciar sesión). Para una app de escritorio de un solo negocio,
   corriendo en una sola computadora, esto es aceptable y mantiene el
   sistema simple; si en el futuro se necesitara que las sesiones
   sobrevivan a un reinicio del backend, se podría mover esta tabla a SQLite.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

PBKDF2_ITERACIONES = 260_000
DURACION_SESION = timedelta(hours=12)


# ---------------------------------------------------------------------------
# Hashing de contraseñas
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Genera un hash seguro de la contraseña, con sal aleatoria incluida."""
    sal = secrets.token_hex(16)
    hash_calculado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(sal), PBKDF2_ITERACIONES
    )
    return f"{sal}${hash_calculado.hex()}"


def verificar_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash almacenado."""
    try:
        sal, hash_guardado = password_hash.split("$")
    except ValueError:
        return False
    hash_calculado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(sal), PBKDF2_ITERACIONES
    )
    # compare_digest evita ataques de timing (comparación en tiempo constante).
    return secrets.compare_digest(hash_calculado.hex(), hash_guardado)


# ---------------------------------------------------------------------------
# Sesiones (tokens de acceso)
# ---------------------------------------------------------------------------

# token -> {"usuario_id": int, "expira": datetime}
_sesiones: dict[str, dict] = {}


def crear_sesion(usuario_id: int) -> str:
    """Crea una nueva sesión para el usuario y devuelve el token generado."""
    token = secrets.token_urlsafe(32)
    _sesiones[token] = {"usuario_id": usuario_id, "expira": datetime.utcnow() + DURACION_SESION}
    return token


def obtener_usuario_id_de_token(token: str) -> int | None:
    """
    Devuelve el id del usuario dueño del token si la sesión es válida y no
    ha expirado (renovándola en el proceso), o None si el token no existe
    o ya expiró.
    """
    sesion = _sesiones.get(token)
    if sesion is None:
        return None
    if datetime.utcnow() > sesion["expira"]:
        del _sesiones[token]
        return None
    sesion["expira"] = datetime.utcnow() + DURACION_SESION  # sliding session
    return sesion["usuario_id"]


def invalidar_sesion(token: str) -> None:
    """Cierra una sesión (logout). No falla si el token ya no existía."""
    _sesiones.pop(token, None)
