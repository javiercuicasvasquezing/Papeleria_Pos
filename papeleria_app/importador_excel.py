"""
importador_excel.py
--------------------
Lógica de importación de productos desde el Excel de inventario real de la
papelería (columnas: MARCA, ARTICULO, CANTIDAD, MEDIDA, UNIDAD,
PRECIO DE LA CAJA, PRECIO DE PAGO, PRECIO 30%+1, Precio de venta).

Interpretación de columnas (confirmada fila por fila contra el archivo
real, no adivinada):
    - MEDIDA = "Caja":  UNIDAD = unidades que trae la caja.
                        CANTIDAD = cajas en stock.
                        stock = CANTIDAD * UNIDAD.
                        PRECIO DE LA CAJA = costo de una caja.
    - MEDIDA = "Unidad": UNIDAD = tamaño del lote de referencia usado para
                        costear (normalmente == CANTIDAD).
                        CANTIDAD = unidades en stock.
                        stock = CANTIDAD.
                        PRECIO DE LA CAJA = costo del lote completo de
                        `UNIDAD` unidades.
    - "Precio de venta" = precio_venta_unidad final (ya decidido).
    - precio_venta_caja = precio_venta_unidad * unidades_por_caja
      (el Excel no trae un precio de caja de venta; así se calcula, por
      decisión del usuario).
    - "PRECIO DE PAGO" y "PRECIO 30%+1" son ayudas de cálculo del dueño,
      no se usan para nada (no son necesarias para poblar el catálogo).
    - No hay columna de código de barras: todos los productos importados
      quedan con codigo_barras = None.
    - No se fusionan artículos con el mismo nombre repetido: cada fila del
      Excel se convierte en un producto independiente (decisión del
      usuario).
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Optional

import openpyxl

COLUMNAS_PROVEEDOR = [
    "MARCA", "ARTICULO", "CANTIDAD", "MEDIDA", "UNIDAD",
    "PRECIO DE LA CAJA", "PRECIO DE PAGO", "PRECIO 30%+1", "Precio de venta",
]
COLUMNAS_EXPORTADO = [
    "Código de barras", "Producto", "Marca", "Precio de compra",
    "Precio venta unidad", "Precio venta caja", "Unidades por caja", "Stock",
]
COLUMNAS_CON_CODIGO = [
    "CODIDO DE BARRA", "RODUCTO", "MARCA", "PRECIO DE COMPRA", "PRECIO 30% + 1",
    "PRECIO VENTA UNIDAD", "PRECIO VENTA  CAJA", "UNIDADES POR CAJA", "STOCK",
]
COLUMNAS_ESPERADAS = COLUMNAS_PROVEEDOR  # compatibilidad con código existente


@dataclass
class FilaImportada:
    fila_excel: int
    marca: Optional[str] = None
    nombre: Optional[str] = None
    codigo_barras: Optional[str] = None
    precio_compra: Optional[str] = None       # como str para no perder precisión decimal
    precio_venta_unidad: Optional[str] = None
    precio_venta_caja: Optional[str] = None
    unidades_por_caja: int = 1
    stock_unidades: int = 0
    error: Optional[str] = None
    advertencia: Optional[str] = None

    @property
    def es_valida(self) -> bool:
        return self.error is None


def _num(valor) -> Optional[float]:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
    except ValueError:
        return None


def _procesar_formato_proveedor(ws) -> list[FilaImportada]:
    filas: list[FilaImportada] = []
    for idx, fila_raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None for v in fila_raw):
            continue

        marca_raw, articulo, cantidad, medida, unidad, precio_caja = fila_raw[:6]
        precio_venta = fila_raw[8] if len(fila_raw) > 8 else None

        fila = FilaImportada(fila_excel=idx)

        nombre = (str(articulo).strip() if articulo is not None else "")
        if not nombre:
            fila.error = "Falta el nombre del artículo."
            filas.append(fila)
            continue
        fila.nombre = nombre
        fila.marca = str(marca_raw).strip() if marca_raw else None

        if medida not in ("Caja", "Unidad"):
            fila.error = f"MEDIDA inválida ('{medida}'); se esperaba 'Caja' o 'Unidad'."
            filas.append(fila)
            continue

        cantidad_n = _num(cantidad)
        unidad_n = _num(unidad)
        precio_caja_n = _num(precio_caja)
        precio_venta_n = _num(precio_venta)

        if cantidad_n is None or cantidad_n < 0:
            fila.error = "CANTIDAD inválida o negativa."
            filas.append(fila)
            continue
        if unidad_n is None or unidad_n <= 0:
            fila.error = "UNIDAD inválida (debe ser mayor a 0)."
            filas.append(fila)
            continue
        if precio_caja_n is None or precio_caja_n < 0:
            fila.error = "PRECIO DE LA CAJA inválido o negativo."
            filas.append(fila)
            continue
        precio_venta_provisional = precio_venta_n is None or precio_venta_n <= 0
        if precio_venta_provisional:
            precio_venta_n = 0.01
            fila.advertencia = "Sin precio de venta en el Excel. Se importó en S/ 0.01 -- revísalo."

        try:
            if medida == "Caja":
                unidades_por_caja = int(unidad_n)
                stock = int(cantidad_n) * unidades_por_caja
                precio_compra = round(precio_caja_n / unidades_por_caja, 2)
                precio_venta_caja = round(precio_venta_n * unidades_por_caja, 2)
            else:  # Unidad
                unidades_por_caja = 1
                stock = int(cantidad_n)
                precio_compra = round(precio_caja_n / unidad_n, 2)
                precio_venta_caja = None
        except (InvalidOperation, ZeroDivisionError) as exc:
            fila.error = f"Error calculando precios: {exc}"
            filas.append(fila)
            continue

        fila.precio_compra = str(Decimal(str(precio_compra)))
        fila.precio_venta_unidad = str(Decimal(str(round(precio_venta_n, 2))))
        fila.precio_venta_caja = str(Decimal(str(precio_venta_caja))) if precio_venta_caja is not None else None
        fila.unidades_por_caja = unidades_por_caja
        fila.stock_unidades = stock

        filas.append(fila)
    return filas


def _procesar_formato_exportado(ws) -> list[FilaImportada]:
    """
    Formato que genera nuestro propio botón 'Exportar Excel':
    Código de barras, Producto, Marca, Precio de compra, Precio venta
    unidad, Precio venta caja, Unidades por caja, Stock.
    Ya viene con los valores finales (sin cálculos que rehacer), así que
    solo se valida y se copia.
    """
    filas: list[FilaImportada] = []
    for idx, fila_raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None for v in fila_raw):
            continue

        (codigo_barras, nombre_raw, marca_raw, precio_compra_raw,
         precio_venta_unidad_raw, precio_venta_caja_raw, unidades_por_caja_raw, stock_raw) = fila_raw[:8]

        fila = FilaImportada(fila_excel=idx)

        nombre = (str(nombre_raw).strip() if nombre_raw is not None else "")
        if not nombre:
            fila.error = "Falta el nombre del producto."
            filas.append(fila)
            continue
        fila.nombre = nombre
        fila.marca = str(marca_raw).strip() if marca_raw else None
        fila.codigo_barras = str(codigo_barras).strip() if codigo_barras else None

        precio_venta_n = _num(precio_venta_unidad_raw)
        if precio_venta_n is None or precio_venta_n <= 0:
            precio_venta_n = 0.01
            fila.advertencia = "Sin precio de venta en el Excel. Se importó en S/ 0.01 -- revísalo."

        precio_compra_n = _num(precio_compra_raw)
        if precio_compra_n is None or precio_compra_n < 0:
            precio_compra_n = 0.0

        stock_n = _num(stock_raw)
        if stock_n is None or stock_n < 0:
            fila.error = "Stock inválido o negativo."
            filas.append(fila)
            continue

        unidades_n = _num(unidades_por_caja_raw)
        unidades_por_caja = int(unidades_n) if unidades_n and unidades_n > 0 else 1

        precio_venta_caja_n = _num(precio_venta_caja_raw)
        # Si no hay una cantidad real de unidades por caja (>1), un precio de
        # caja suelto no es válido para el sistema -- se descarta en vez de
        # guardar una combinación inconsistente que rompería /productos/.
        if unidades_por_caja <= 1:
            precio_venta_caja_n = None

        fila.precio_compra = str(Decimal(str(round(precio_compra_n, 2))))
        fila.precio_venta_unidad = str(Decimal(str(round(precio_venta_n, 2))))
        fila.precio_venta_caja = (
            str(Decimal(str(round(precio_venta_caja_n, 2)))) if precio_venta_caja_n else None
        )
        fila.unidades_por_caja = unidades_por_caja
        fila.stock_unidades = int(stock_n)

        filas.append(fila)
    return filas


def _procesar_formato_con_codigo(ws) -> list[FilaImportada]:
    """
    Formato: CODIDO DE BARRA, RODUCTO, MARCA, PRECIO DE COMPRA,
    PRECIO 30% + 1 (se ignora, solo es ayuda de cálculo), PRECIO VENTA
    UNIDAD, PRECIO VENTA CAJA, UNIDADES POR CAJA, STOCK.
    Incluye validación automática para corregir precios de caja ilógicos.
    """
    filas: list[FilaImportada] = []
    for idx, fila_raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None for v in fila_raw):
            continue

        (codigo_barras, nombre_raw, marca_raw, precio_compra_raw, _precio_30_mas_1,
         precio_venta_unidad_raw, precio_venta_caja_raw, unidades_por_caja_raw, stock_raw) = fila_raw[:9]

        fila = FilaImportada(fila_excel=idx)

        nombre = (str(nombre_raw).strip() if nombre_raw is not None else "")
        if not nombre:
            fila.error = "Falta el nombre del producto."
            filas.append(fila)
            continue
        fila.nombre = nombre
        fila.marca = str(marca_raw).strip() if marca_raw else None
        fila.codigo_barras = str(codigo_barras).strip() if codigo_barras else None

        # 1. Validación de Precio Venta Unidad
        precio_venta_n = _num(precio_venta_unidad_raw)
        if precio_venta_n is None or precio_venta_n <= 0:
            precio_venta_n = 0.01
            fila.advertencia = "Sin precio de venta en el Excel. Se importó en S/ 0.01 -- revísalo."

        # 2. Validación de Precio Compra
        precio_compra_n = _num(precio_compra_raw)
        if precio_compra_n is None or precio_compra_n < 0:
            precio_compra_n = 0.0

        # 3. Validación de Stock
        stock_n = _num(stock_raw)
        if stock_n is None or stock_n < 0:
            fila.error = "Stock inválido o negativo."
            filas.append(fila)
            continue

        # 4. Unidades por caja
        unidades_n = _num(unidades_por_caja_raw)
        unidades_por_caja = int(unidades_n) if unidades_n and unidades_n > 0 else 1

        # 5. Validación inteligente del Precio Venta Caja
        precio_venta_caja_n = _num(precio_venta_caja_raw)
        
        if unidades_por_caja > 1:
            # Si el precio de caja registrado es menor o igual al unitario, 
            # significa que el dato en el Excel es erróneo o costo unitario. 
            # Lo recalculamos automáticamente de forma lógica.
            if precio_venta_caja_n is None or precio_venta_caja_n <= precio_venta_n:
                precio_venta_caja_n = round(precio_venta_n * unidades_por_caja, 2)
                fila.advertencia = "Precio de caja corregido automáticamente por inconsistencia numérica."
        else:
            precio_venta_caja_n = None

        # Asignación de valores limpios
        fila.precio_compra = str(Decimal(str(round(precio_compra_n, 2))))
        fila.precio_venta_unidad = str(Decimal(str(round(precio_venta_n, 2))))
        fila.precio_venta_caja = (
            str(Decimal(str(round(precio_venta_caja_n, 2)))) if precio_venta_caja_n else None
        )
        fila.unidades_por_caja = unidades_por_caja
        fila.stock_unidades = int(stock_n)

        filas.append(fila)
    return filas


def procesar_archivo_excel(contenido: bytes) -> tuple[list[FilaImportada], Optional[str]]:
    """
    Parsea el archivo .xlsx y devuelve (filas, error_general).
    Reconoce automáticamente DOS formatos:
        1. El del proveedor (MARCA, ARTICULO, CANTIDAD, MEDIDA, UNIDAD...).
        2. El que genera nuestro propio "Exportar Excel" (Código de barras,
           Producto, Marca, Precio de compra...) -- así el archivo que el
           negocio exporta hoy se puede reimportar sin error mañana.
    Si error_general no es None, el archivo no coincide con ninguno de los
    dos formatos conocidos y no se procesó ninguna fila.
    """
    try:
        wb = openpyxl.load_workbook(BytesIO(contenido), data_only=True)
    except Exception as exc:
        return [], f"No se pudo abrir el archivo: {exc}"

    ws = wb[wb.sheetnames[0]]
    encabezados = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]

    if encabezados[:9] == COLUMNAS_PROVEEDOR:
        return _procesar_formato_proveedor(ws), None

    if encabezados[:8] == COLUMNAS_EXPORTADO:
        return _procesar_formato_exportado(ws), None

    if encabezados[:9] == COLUMNAS_CON_CODIGO:
        return _procesar_formato_con_codigo(ws), None

    return [], (
        "El archivo no tiene columnas reconocidas. Se acepta el formato del "
        f"proveedor ({', '.join(COLUMNAS_PROVEEDOR)}) o el formato exportado "
        f"por esta misma app ({', '.join(COLUMNAS_EXPORTADO)}). "
        f"Se encontró: {', '.join(encabezados)}"
    )
