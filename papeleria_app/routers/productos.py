"""
routers/productos.py
---------------------
Endpoints de la API para el catálogo de productos y el manejo de inventario.

Endpoints incluidos (Módulo 2):
    POST /productos/            -> Registrar un nuevo producto.
    GET  /productos/             -> Listar productos (paginado, filtro opcional por marca).
    GET  /productos/buscar/      -> Buscar por texto libre (nombre) y/o código de barras exacto.
    PUT  /productos/{id}         -> Actualizar stock y/o precios (actualización parcial).

Todas las reglas de validación de "forma" de los datos (tipos, rangos, campos
obligatorios) viven en schemas.py (Pydantic). Aquí solo se resuelven reglas que
dependen del ESTADO de la base de datos: unicidad de código de barras,
existencia del producto, etc.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from importador_excel import procesar_archivo_excel
from models import DetalleVenta, Producto
from routers.auth import obtener_usuario_actual
import schemas

router = APIRouter(prefix="/productos", tags=["Productos"], dependencies=[Depends(obtener_usuario_actual)])


# ---------------------------------------------------------------------------
# POST /productos/  -> Registrar un nuevo producto
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=schemas.ProductoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo producto",
)
def crear_producto(producto_in: schemas.ProductoCreate, db: Session = Depends(get_db)):
    """
    Crea un producto en el catálogo.

    - `precio_venta_unidad` es obligatorio (todo producto se vende al menos por unidad).
    - `precio_venta_caja` y `unidades_por_caja` son opcionales: solo se definen si el
      producto también se vende por caja/paquete.
    - `codigo_barras` es opcional, pero si se envía debe ser único en el catálogo.
    """
    nuevo_producto = Producto(**producto_in.model_dump())

    db.add(nuevo_producto)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Distinguimos el mensaje según qué restricción única fue la que falló,
        # para dar una respuesta clara al cliente de la API.
        detalle = "Ya existe un producto con ese código de barras." \
            if "codigo_barras" in str(exc.orig) else \
            "No se pudo crear el producto por un conflicto de datos únicos."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle) from exc

    db.refresh(nuevo_producto)
    return nuevo_producto


# ---------------------------------------------------------------------------
# GET /productos/  -> Listar productos (paginado + filtro por marca)
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=schemas.ProductoListaOut,
    summary="Listar productos",
)
def listar_productos(
    skip: int = Query(default=0, ge=0, description="Cantidad de registros a saltar (paginación)."),
    limit: int = Query(default=50, ge=1, le=200, description="Cantidad máxima de registros a devolver."),
    marca: Optional[str] = Query(default=None, description="Filtrar por marca exacta."),
    db: Session = Depends(get_db),
):
    """
    Devuelve el catálogo de productos, con paginación simple (`skip`/`limit`)
    y un filtro opcional por marca exacta.
    """
    consulta = db.query(Producto)

    if marca:
        consulta = consulta.filter(Producto.marca == marca)

    total = consulta.count()
    items = (
        consulta.order_by(Producto.nombre.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# GET /productos/buscar/  -> Búsqueda por texto y/o código de barras
# ---------------------------------------------------------------------------

@router.get(
    "/buscar/",
    response_model=schemas.ProductoListaOut,
    summary="Buscar productos por texto o código de barras",
)
def buscar_productos(
    q: Optional[str] = Query(
        default=None,
        min_length=1,
        description="Texto a buscar en el nombre del producto (búsqueda parcial, sin distinguir mayúsculas).",
    ),
    codigo_barras: Optional[str] = Query(
        default=None,
        description="Código de barras exacto a buscar (uso típico: lector de código de barras del POS).",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Búsqueda pensada para el punto de venta:
    - Si se envía `codigo_barras`, se prioriza la coincidencia exacta (uso con
      lector de código de barras), típicamente esperando 0 o 1 resultado.
    - Si se envía `q`, se busca coincidencia parcial en el nombre (para cuando
      el vendedor escribe el nombre del producto manualmente).
    - Se puede combinar ambos (funcionan como filtros AND) o usar solo uno.
    - Se requiere al menos uno de los dos parámetros.
    """
    if not q and not codigo_barras:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar al menos 'q' (texto) o 'codigo_barras' para buscar.",
        )

    consulta = db.query(Producto)

    if codigo_barras:
        consulta = consulta.filter(Producto.codigo_barras == codigo_barras)

    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(Producto.nombre.ilike(patron))

    items = consulta.order_by(Producto.nombre.asc()).limit(limit).all()

    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# PUT /productos/{id}  -> Actualizar stock y/o precios
# ---------------------------------------------------------------------------

@router.put(
    "/{producto_id}",
    response_model=schemas.ProductoOut,
    summary="Actualizar un producto (stock y/o precios)",
)
def actualizar_producto(
    producto_id: int,
    producto_in: schemas.ProductoUpdate,
    db: Session = Depends(get_db),
):
    """
    Actualiza parcialmente un producto existente (solo se modifican los campos
    enviados en el body). Pensado para dos casos de uso principales:
        1. Ajustar stock (ej. tras una compra a proveedor o un conteo físico).
        2. Actualizar precios de compra/venta (unidad y/o caja).

    Nota: este endpoint hace una actualización DIRECTA de `stock_unidades`
    (lo reemplaza por el valor enviado). El descuento automático de stock por
    ventas se maneja en el motor de ventas del Módulo 4, no aquí.
    """
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe un producto con id={producto_id}.",
        )

    datos_nuevos = producto_in.model_dump(exclude_unset=True)

    # Validamos la coherencia caja/unidades_por_caja considerando el estado
    # FINAL del producto (mezclando lo que ya tenía con lo que se está
    # actualizando), no solo los campos que llegan en este request.
    precio_venta_caja_final = datos_nuevos.get("precio_venta_caja", producto.precio_venta_caja)
    unidades_por_caja_final = datos_nuevos.get("unidades_por_caja", producto.unidades_por_caja)
    if precio_venta_caja_final is not None and unidades_por_caja_final <= 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Si el producto tiene 'precio_venta_caja', 'unidades_por_caja' debe ser mayor a 1.",
        )

    for campo, valor in datos_nuevos.items():
        setattr(producto, campo, valor)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        detalle = "Ya existe otro producto con ese código de barras." \
            if "codigo_barras" in str(exc.orig) else \
            "No se pudo actualizar el producto por un conflicto de datos únicos."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle) from exc

    db.refresh(producto)
    return producto


def _clave(nombre: str, marca: Optional[str]) -> tuple:
    return (nombre.strip().lower(), (marca or "").strip().lower())


@router.post(
    "/importar/vista-previa",
    response_model=schemas.VistaPreviaImportacionOut,
    summary="Analizar un Excel de inventario antes de importarlo",
)
async def vista_previa_importacion(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Compara cada fila del Excel contra el catálogo actual usando
    (nombre, marca) normalizados como clave -- el Excel de este negocio no
    trae código de barras, así que no puede usarse como identificador único
    (decisión acordada explícitamente, no un supuesto).
    """
    contenido = await archivo.read()
    filas, error_general = procesar_archivo_excel(contenido)

    if error_general:
        return {"total": 0, "nuevos": 0, "existentes": 0, "con_errores": 0, "filas": [], "error_general": error_general}

    existentes_por_clave = {_clave(p.nombre, p.marca): p.id for p in db.query(Producto).all()}

    for f in filas:
        if not f.es_valida:
            continue
        producto_id = existentes_por_clave.get(_clave(f.nombre, f.marca))
        if producto_id:
            f.accion = "actualizar"
            f.producto_existente_id = producto_id
        else:
            f.accion = "crear"

    validas = [f for f in filas if f.es_valida]
    con_error = [f for f in filas if not f.es_valida]
    nuevos = [f for f in validas if f.accion == "crear"]
    existentes = [f for f in validas if f.accion == "actualizar"]

    return {
        "total": len(filas),
        "nuevos": len(nuevos),
        "existentes": len(existentes),
        "con_errores": len(con_error),
        "filas": [f.__dict__ for f in filas],
        "error_general": None,
    }


@router.post(
    "/importar/confirmar",
    response_model=schemas.ConfirmarImportacionOut,
    summary="Confirmar la importación",
)
def confirmar_importacion(datos: schemas.ConfirmarImportacionRequest, db: Session = Depends(get_db)):
    """
    Modo 'agregar_nuevos': solo crea productos nuevos; los que ya existen
    (mismo nombre+marca) se omiten sin tocarlos.
    Modo 'actualizar_y_crear': crea los nuevos y actualiza precios/marca/
    unidades_por_caja de los existentes. El stock solo se toca si
    `actualizar_stock=True` (por defecto NO, para no pisar ventas hechas
    desde la última importación).
    Todo ocurre en una sola transacción: si algo falla, no se guarda nada.
    """
    nuevos, actualizados, omitidos = 0, 0, 0
    try:
        for fila in datos.filas:
            if fila.error is not None:
                continue
            if fila.accion == "crear":
                db.add(Producto(
                    codigo_barras=None, nombre=fila.nombre, marca=fila.marca,
                    precio_compra=fila.precio_compra or "0",
                    precio_venta_unidad=fila.precio_venta_unidad,
                    precio_venta_caja=fila.precio_venta_caja,
                    unidades_por_caja=fila.unidades_por_caja,
                    stock_unidades=fila.stock_unidades,
                ))
                nuevos += 1
            elif fila.accion == "actualizar":
                if datos.modo != "actualizar_y_crear":
                    omitidos += 1
                    continue
                producto = db.get(Producto, fila.producto_existente_id)
                if producto is None:
                    continue
                producto.marca = fila.marca
                producto.precio_compra = fila.precio_compra or "0"
                producto.precio_venta_unidad = fila.precio_venta_unidad
                producto.precio_venta_caja = fila.precio_venta_caja
                producto.unidades_por_caja = fila.unidades_por_caja
                if datos.actualizar_stock:
                    producto.stock_unidades = fila.stock_unidades
                actualizados += 1
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "No se pudo completar la importación. No se guardó nada.") from exc

    return {"nuevos": nuevos, "actualizados": actualizados, "omitidos": omitidos}


@router.post(
    "/importar/reemplazar-todo",
    response_model=schemas.ReemplazarTodoOut,
    summary="Eliminar todo el inventario e importar desde cero (solo administradores)",
)
def reemplazar_todo(datos: schemas.ReemplazarTodoRequest, db: Session = Depends(get_db),
                     usuario_actual=Depends(obtener_usuario_actual)):
    if usuario_actual.rol.value != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta acción requiere privilegios de administrador.")
    if datos.confirmacion.strip() != "CONFIRMAR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debes escribir CONFIRMAR para continuar.")

    # No se puede eliminar un producto que ya tiene ventas registradas (la
    # llave foránea lo impide, y con razón: se perdería el historial). Esos
    # productos se conservan tal cual; el resto sí se borra.
    ids_con_ventas = {row[0] for row in db.query(DetalleVenta.producto_id).distinct().all()}
    todos = db.query(Producto).all()
    eliminados = 0
    conservados = 0
    for p in todos:
        if p.id in ids_con_ventas:
            conservados += 1
            continue
        db.delete(p)
        eliminados += 1
    db.commit()

    nuevos = 0
    for fila in datos.filas:
        if fila.error is not None or fila.accion == "omitir":
            continue
        db.add(Producto(
            codigo_barras=None, nombre=fila.nombre, marca=fila.marca,
            precio_compra=fila.precio_compra or "0",
            precio_venta_unidad=fila.precio_venta_unidad,
            precio_venta_caja=fila.precio_venta_caja,
            unidades_por_caja=fila.unidades_por_caja,
            stock_unidades=fila.stock_unidades,
        ))
        nuevos += 1
    db.commit()

    return {"eliminados": eliminados, "conservados_por_tener_ventas": conservados, "nuevos": nuevos}


# ---------------------------------------------------------------------------
# Eliminar productos (uno o varios)
# ---------------------------------------------------------------------------

@router.post(
    "/eliminar",
    response_model=schemas.EliminarProductosOut,
    summary="Eliminar uno o varios productos (los que tengan ventas no se eliminan)",
)
def eliminar_productos(datos: schemas.EliminarProductosRequest, db: Session = Depends(get_db)):
    ids_con_ventas = {row[0] for row in db.query(DetalleVenta.producto_id).filter(
        DetalleVenta.producto_id.in_(datos.ids)
    ).distinct().all()}

    eliminados = 0
    no_eliminables = []
    for pid in datos.ids:
        if pid in ids_con_ventas:
            producto = db.get(Producto, pid)
            no_eliminables.append({
                "id": pid,
                "nombre": producto.nombre if producto else "?",
                "motivo": "Tiene ventas registradas. Puedes marcarlo como Inactivo en su lugar.",
            })
            continue
        producto = db.get(Producto, pid)
        if producto:
            db.delete(producto)
            eliminados += 1
    db.commit()
    return {"eliminados": eliminados, "no_eliminables": no_eliminables}


# ---------------------------------------------------------------------------
# GET /productos/exportar-excel  -> Descarga el catálogo completo en .xlsx
# ---------------------------------------------------------------------------

@router.get("/exportar-excel", summary="Exportar el catálogo completo a Excel")
def exportar_excel(db: Session = Depends(get_db)):
    import io
    import openpyxl
    from fastapi.responses import StreamingResponse

    productos = db.query(Producto).order_by(Producto.nombre).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventario"
    ws.append([
        "Código de barras", "Producto", "Marca", "Precio de compra",
        "Precio venta unidad", "Precio venta caja", "Unidades por caja", "Stock",
    ])
    for p in productos:
        ws.append([
            p.codigo_barras or "", p.nombre, p.marca or "",
            float(p.precio_compra), float(p.precio_venta_unidad),
            float(p.precio_venta_caja) if p.precio_venta_caja is not None else "",
            p.unidades_por_caja, p.stock_unidades,
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=inventario_exportado.xlsx"},
    )
