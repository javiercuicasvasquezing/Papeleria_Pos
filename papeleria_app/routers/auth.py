"""
routers/auth.py
----------------
Autenticación (Módulo de Usuarios). Contiene:
    - Los endpoints POST /auth/login, POST /auth/logout, GET /auth/me.
    - Las DEPENDENCIAS reutilizables `obtener_usuario_actual` y
      `requerir_admin`, que el resto de los routers (productos, clientes,
      ventas, usuarios) importan para exigir sesión iniciada -- y, en el
      caso de `requerir_admin`, además exigir rol de administrador.

Cómo funciona la protección de endpoints:
    Cada router protegido se declara así:
        router = APIRouter(prefix="/productos", dependencies=[Depends(obtener_usuario_actual)])
    Eso hace que TODAS las rutas de ese router exijan un header
    `Authorization: Bearer <token>` válido antes de ejecutarse. Si falta o
    es inválido, FastAPI responde 401 automáticamente sin llegar siquiera
    al código del endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import RolUsuario, Usuario
from security import crear_sesion, hash_password, invalidar_sesion, obtener_usuario_id_de_token, verificar_password
import schemas

router = APIRouter(prefix="/auth", tags=["Autenticación"])


# ---------------------------------------------------------------------------
# Dependencias de autenticación / autorización (usadas por otros routers)
# ---------------------------------------------------------------------------

def obtener_usuario_actual(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Extrae y valida el token del header `Authorization: Bearer <token>`, y
    devuelve el usuario dueño de la sesión. Lanza 401 si no hay token, el
    token es inválido/expiró, o el usuario fue desactivado mientras tanto.
    """
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado. Inicia sesión para continuar.",
    )

    if authorization is None or not authorization.startswith("Bearer "):
        raise credenciales_invalidas

    token = authorization.removeprefix("Bearer ").strip()
    usuario_id = obtener_usuario_id_de_token(token)
    if usuario_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tu sesión expiró o no es válida. Inicia sesión nuevamente.",
        )

    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise credenciales_invalidas

    return usuario


def requerir_admin(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
    """Como `obtener_usuario_actual`, pero además exige rol ADMIN (403 si no lo es)."""
    if usuario_actual.rol != RolUsuario.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta acción requiere privilegios de administrador.",
        )
    return usuario_actual


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=schemas.LoginResponse, summary="Iniciar sesión")
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.username == datos.username.strip().lower()).first()

    # Mensaje deliberadamente genérico (no decimos si falló el usuario o la
    # contraseña) para no ayudar a un atacante a enumerar usuarios válidos.
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Usuario o contraseña incorrectos.",
    )

    if usuario is None or not verificar_password(datos.password, usuario.password_hash):
        raise credenciales_invalidas

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este usuario está desactivado. Contacta a un administrador.",
        )

    token = crear_sesion(usuario.id)
    return {"token": token, "usuario": usuario}


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar sesión")
def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        invalidar_sesion(authorization.removeprefix("Bearer ").strip())
    return None


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=schemas.UsuarioOut, summary="Datos del usuario autenticado")
def me(usuario_actual: Usuario = Depends(obtener_usuario_actual)):
    """
    Devuelve los datos del usuario dueño del token enviado. Útil para que la
    interfaz de escritorio valide, al arrancar, si una sesión guardada
    sigue siendo válida antes de mostrar la pantalla principal.
    """
    return usuario_actual


# ---------------------------------------------------------------------------
# GET /auth/existe-algun-usuario
# ---------------------------------------------------------------------------

@router.get(
    "/existe-algun-usuario",
    summary="Indica si ya existe al menos un usuario registrado",
)
def existe_algun_usuario(db: Session = Depends(get_db)):
    """
    Endpoint público (no requiere sesión) usado por la pantalla de "Crear
    usuario" del login para saber si está tratando con la instalación
    "en blanco" (primer usuario del sistema, se permite crear un ADMIN
    libremente) o si ya hay usuarios (crear otro ADMIN exige autorización).
    """
    hay_usuarios = db.query(Usuario).first() is not None
    return {"hay_usuarios": hay_usuarios}


# ---------------------------------------------------------------------------
# POST /auth/registro
# ---------------------------------------------------------------------------

@router.post(
    "/registro",
    response_model=schemas.UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo usuario desde la pantalla de login",
)
def registro(datos: schemas.RegistroUsuarioRequest, db: Session = Depends(get_db)):
    """
    Crea un usuario SIN requerir sesión iniciada -- es lo que usa el botón
    "Crear usuario" de la pantalla de login.

    Reglas de autorización:
        - rol CAJERO: siempre permitido, autoservicio libre.
        - rol ADMIN, y todavía no existe ningún usuario en el sistema:
          permitido libremente (bootstrap: es el primer usuario que
          configura la app, normalmente el dueño del negocio).
        - rol ADMIN, y ya existen usuarios: exige `admin_username` +
          `admin_password` de un administrador activo ya existente.
    """
    if db.query(Usuario).filter(Usuario.username == datos.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el nombre de usuario '{datos.username}'.",
        )

    if datos.rol == "ADMIN":
        ya_hay_usuarios = db.query(Usuario).first() is not None
        if ya_hay_usuarios:
            if not datos.admin_username or not datos.admin_password:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Para crear otro administrador debes ingresar el usuario y "
                        "la contraseña de un administrador ya existente."
                    ),
                )
            admin_autoriza = (
                db.query(Usuario)
                .filter(Usuario.username == datos.admin_username.strip().lower())
                .first()
            )
            autorizado = (
                admin_autoriza is not None
                and admin_autoriza.activo
                and admin_autoriza.rol == RolUsuario.ADMIN
                and verificar_password(datos.admin_password, admin_autoriza.password_hash)
            )
            if not autorizado:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Las credenciales de administrador ingresadas no son válidas.",
                )
        # Si ya_hay_usuarios es False: es el primer usuario del sistema,
        # se permite crear el ADMIN inicial sin ninguna autorización extra.

    nuevo_usuario = Usuario(
        username=datos.username,
        password_hash=hash_password(datos.password),
        nombre_completo=datos.nombre_completo,
        rol=RolUsuario(datos.rol),
        activo=True,
    )
    db.add(nuevo_usuario)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el nombre de usuario '{datos.username}'.",
        ) from exc

    db.refresh(nuevo_usuario)
    return nuevo_usuario
