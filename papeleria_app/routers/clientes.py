"""
routers/clientes.py
--------------------
Endpoints de la API para el registro y consulta de clientes.

Endpoints incluidos (Módulo 3):
    POST /clientes/               -> Registrar un cliente (registro opcional/básico).
    GET  /clientes/{documento}    -> Consultar un cliente por su número de documento
                                      (DNI o RUC).

Recordatorio de negocio: el registro de cliente es OPCIONAL a nivel de venta
(una venta puede hacerse sin cliente asociado). Estos endpoints existen para
los casos en que sí se quiere guardar el dato del cliente, ya sea para
facturación posterior, historial de compras, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Cliente
from routers.auth import obtener_usuario_actual
import schemas

router = APIRouter(prefix="/clientes", tags=["Clientes"], dependencies=[Depends(obtener_usuario_actual)])


# ---------------------------------------------------------------------------
# POST /clientes/  -> Registrar un cliente
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=schemas.ClienteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un cliente",
)
def crear_cliente(cliente_in: schemas.ClienteCreate, db: Session = Depends(get_db)):
    """
    Registra un cliente. Todo el bloque de documento (`tipo_documento` +
    `numero_documento`) es opcional -- pensado para ventas rápidas de
    mostrador donde no se pide identificación -- pero si se envía uno de los
    dos campos, el otro se vuelve obligatorio (validado en schemas.py).

    Si `numero_documento` ya existe para otro cliente, se responde 409
    (Conflict) en vez de dejar que la base de datos lance un error genérico.
    """
    nuevo_cliente = Cliente(**cliente_in.model_dump())

    db.add(nuevo_cliente)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente registrado con ese número de documento.",
        ) from exc

    db.refresh(nuevo_cliente)
    return nuevo_cliente


# ---------------------------------------------------------------------------
# GET /clientes/{documento}  -> Consultar cliente por número de documento
# ---------------------------------------------------------------------------

@router.get(
    "/{documento}",
    response_model=schemas.ClienteOut,
    summary="Consultar un cliente por número de documento",
)
def obtener_cliente_por_documento(documento: str, db: Session = Depends(get_db)):
    """
    Busca un cliente por su número de documento exacto (DNI o RUC).

    Caso de uso típico en el POS: el vendedor escribe o escanea el DNI/RUC del
    cliente antes de cerrar la venta, para autocompletar sus datos si ya
    estaba registrado.
    """
    cliente = (
        db.query(Cliente)
        .filter(Cliente.numero_documento == documento)
        .first()
    )
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe un cliente registrado con el documento '{documento}'.",
        )
    return cliente
