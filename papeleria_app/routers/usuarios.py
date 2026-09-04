"""
routers/usuarios.py
--------------------
Gestión de usuarios del sistema. TODO este router exige rol de administrador
(ver `dependencies=[Depends(requerir_admin)]` en la definición del router
más abajo) -- un vendedor autenticado NO puede crear ni listar usuarios.

Endpoints:
    POST /usuarios/   -> Crear un nuevo usuario (username, contraseña, rol).
    GET  /usuarios/    -> Listar los usuarios registrados.

Nota: para crear el PRIMER usuario administrador del sistema (cuando la
tabla de usuarios está vacía) no se puede usar este endpoint, porque
requiere estar ya autenticado como admin -- para eso existe el script de
arranque `crear_usuario.py`, que crea usuarios directamente en la base de
datos sin pasar por la API.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from routers.auth import requerir_admin
from security import hash_password
import schemas

router = APIRouter(prefix="/usuarios", tags=["Usuarios"], dependencies=[Depends(requerir_admin)])


@router.post(
    "/",
    response_model=schemas.UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo usuario (solo administradores)",
)
def crear_usuario(datos: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    nuevo_usuario = Usuario(
        username=datos.username,
        password_hash=hash_password(datos.password),
        nombre_completo=datos.nombre_completo,
        rol=datos.rol,
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


@router.get(
    "/",
    response_model=list[schemas.UsuarioOut],
    summary="Listar usuarios (solo administradores)",
)
def listar_usuarios(db: Session = Depends(get_db)):
    return db.query(Usuario).order_by(Usuario.username).all()
