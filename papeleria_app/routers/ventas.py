"""
routers/ventas.py
------------------
Motor de ventas (POS) del Sistema de Librería/Papelería.

Endpoint incluido (Módulo 4):
    POST /ventas/  -> Registrar una venta completa (una o más líneas de
                       productos) con su pago, de forma atómica.

Garantías que ofrece este endpoint:
    1. ATOMICIDAD: la venta se registra completa o no se registra nada. Si
       CUALQUIER línea falla (producto inexistente, sin stock, modalidad de
       venta no disponible para ese producto), NO se descuenta stock de
       NINGÚN producto ni se crea la venta. Esto se logra:
           a) Validando y calculando TODO primero (sin escribir en la BD).
           b) Recién al final, si todo es válido, se aplican los cambios
              (crear Venta + DetalleVenta + descontar stock) y se hace UN
              solo `db.commit()`.
           c) Si algo falla en ese commit (ej. una condición de carrera),
              se hace `rollback()` y no queda nada a medias.
    2. CONVERSIÓN CAJA -> UNIDADES: si una línea se vende por CAJA, el stock
       se descuenta en `cantidad_cajas * unidades_por_caja` (unidades base),
       nunca en "cajas".
    3. PRECIOS DE SERVIDOR: el precio unitario y el total NUNCA se toman del
       request del cliente; se resuelven siempre desde el catálogo
       (`Producto.precio_venta_unidad` / `Producto.precio_venta_caja`)
       vigente en el momento de la venta.
    4. VALIDACIÓN DE PAGO:
           - EFECTIVO: `monto_recibido` debe ser >= `total`; se calcula el
             `vuelto` automáticamente.
           - YAPE: `referencia_pago` (número de operación) no puede repetirse
             con ninguna venta anterior (anti-fraude / anti-duplicidad).

Nota sobre concurrencia: SQLite serializa las escrituras a nivel de archivo
(un solo escritor a la vez), lo cual es suficiente para una app de escritorio
local de un solo negocio. Si en el futuro se migrara a un motor
multi-usuario (PostgreSQL, por ejemplo), este mismo flujo debería reforzarse
con un `SELECT ... FOR UPDATE` sobre las filas de `productos` al leer el
stock, para evitar condiciones de carrera entre cajeros concurrentes.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Cliente, DetalleVenta, Producto, Venta
from routers.auth import obtener_usuario_actual
import schemas

router = APIRouter(prefix="/ventas", tags=["Ventas"], dependencies=[Depends(obtener_usuario_actual)])


@router.post(
    "/",
    response_model=schemas.VentaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una venta (POS)",
)
def crear_venta(venta_in: schemas.VentaCreate, db: Session = Depends(get_db)):
    # -----------------------------------------------------------------
    # 0. Validar cliente (si se indicó uno)
    # -----------------------------------------------------------------
    if venta_in.cliente_id is not None:
        cliente = db.get(Cliente, venta_in.cliente_id)
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe un cliente con id={venta_in.cliente_id}.",
            )

    # -----------------------------------------------------------------
    # 1. FASE DE VALIDACIÓN Y CÁLCULO (sin tocar la base de datos todavía)
    #    Se resuelve cada línea: producto, precio vigente, unidades a
    #    descontar del stock, y se verifica que haya stock suficiente.
    #    Si cualquier línea falla, se aborta ANTES de escribir nada.
    # -----------------------------------------------------------------
    lineas_resueltas = []  # lista de dicts con todo lo necesario para persistir después
    total = Decimal("0")

    for idx, detalle in enumerate(venta_in.detalles, start=1):
        producto = db.get(Producto, detalle.producto_id)
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Línea {idx}: no existe un producto con id={detalle.producto_id}.",
            )

        if detalle.tipo_venta == "CAJA":
            if producto.precio_venta_caja is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Línea {idx}: el producto '{producto.nombre}' no tiene precio "
                        "definido para venta por caja."
                    ),
                )
            precio_unitario_aplicado = producto.precio_venta_caja
            unidades_a_descontar = detalle.cantidad * producto.unidades_por_caja
        else:  # UNIDAD
            precio_unitario_aplicado = producto.precio_venta_unidad
            unidades_a_descontar = detalle.cantidad

        if producto.stock_unidades < unidades_a_descontar:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Línea {idx}: stock insuficiente para '{producto.nombre}'. "
                    f"Disponible: {producto.stock_unidades} unidad(es), "
                    f"solicitado: {unidades_a_descontar} unidad(es). "
                    "La venta fue cancelada por completo (no se descontó nada)."
                ),
            )

        subtotal = (precio_unitario_aplicado * detalle.cantidad).quantize(Decimal("0.01"))
        total += subtotal

        lineas_resueltas.append(
            {
                "producto": producto,
                "tipo_venta": detalle.tipo_venta,
                "cantidad": detalle.cantidad,
                "precio_unitario_aplicado": precio_unitario_aplicado,
                "subtotal": subtotal,
                "unidades_a_descontar": unidades_a_descontar,
            }
        )

    total = total.quantize(Decimal("0.01"))

    # -----------------------------------------------------------------
    # 2. VALIDACIÓN DEL PAGO (usando el total ya calculado por el servidor)
    # -----------------------------------------------------------------
    vuelto = None

    if venta_in.metodo_pago == "EFECTIVO":
        if venta_in.monto_recibido < total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"El monto recibido (S/ {venta_in.monto_recibido}) es menor al "
                    f"total de la venta (S/ {total})."
                ),
            )
        vuelto = (venta_in.monto_recibido - total).quantize(Decimal("0.01"))

    else:  # YAPE
        if venta_in.referencia_pago:
            referencia_existente = (
                db.query(Venta)
                .filter(Venta.referencia_pago == venta_in.referencia_pago)
                .first()
            )
            if referencia_existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"El número de operación Yape '{venta_in.referencia_pago}' ya fue "
                        "registrado en otra venta (posible pago duplicado)."
                    ),
                )

    # -----------------------------------------------------------------
    # 3. FASE DE ESCRITURA: recién aquí se modifica la base de datos.
    #    Todo dentro de una sola transacción -> o se guarda todo, o nada.
    # -----------------------------------------------------------------
    nueva_venta = Venta(
        cliente_id=venta_in.cliente_id,
        total=total,
        metodo_pago=venta_in.metodo_pago,
        monto_recibido=venta_in.monto_recibido if venta_in.metodo_pago == "EFECTIVO" else None,
        vuelto=vuelto,
        referencia_pago=venta_in.referencia_pago if venta_in.metodo_pago == "YAPE" else None,
    )
    db.add(nueva_venta)

    for linea in lineas_resueltas:
        producto = linea["producto"]

        # Descuento de stock, siempre en unidades base.
        producto.stock_unidades -= linea["unidades_a_descontar"]

        detalle_venta = DetalleVenta(
            venta=nueva_venta,
            producto_id=producto.id,
            tipo_venta=linea["tipo_venta"],
            cantidad=linea["cantidad"],
            precio_unitario_aplicado=linea["precio_unitario_aplicado"],
            subtotal=linea["subtotal"],
        )
        db.add(detalle_venta)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Cubre condiciones de carrera: ej. dos requests casi simultáneos con
        # la misma referencia_pago que pasaron ambos la validación de arriba,
        # pero el índice único de la base de datos solo deja pasar a uno.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se pudo registrar la venta por un conflicto de datos "
                "(posible referencia de pago duplicada). Intenta nuevamente."
            ),
        ) from exc

    db.refresh(nueva_venta)

    # Adjuntamos el nombre del producto en cada línea de salida (comodidad
    # para la interfaz de escritorio, para no requerir una consulta aparte).
    for detalle_venta, linea in zip(nueva_venta.detalles, lineas_resueltas):
        detalle_venta.producto_nombre = linea["producto"].nombre

    return nueva_venta
