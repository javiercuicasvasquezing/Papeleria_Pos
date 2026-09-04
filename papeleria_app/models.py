"""
models.py
---------
Modelos ORM (SQLAlchemy) para el Sistema POS de Librería/Papelería.

Tablas definidas:
    - Producto        -> catálogo e inventario (soporta venta por UNIDAD y por CAJA).
    - Cliente          -> registro opcional de clientes (DNI/RUC).
    - Venta            -> cabecera de cada transacción (pago EFECTIVO o YAPE).
    - DetalleVenta     -> líneas de cada venta (uno o más productos por venta).

Decisiones de diseño clave:
    1. El stock SIEMPRE se maneja en unidades base (`stock_unidades`). Cuando se vende
       por caja, el Módulo 4 (motor de ventas) se encargará de multiplicar
       `cantidad_cajas * unidades_por_caja` antes de descontar del stock. Este módulo
       solo define la estructura; la lógica de conversión vive en el módulo de ventas.
    2. Se usan `Enum` de Python nativos (con `sqlalchemy.Enum`) para restringir los
       valores de `metodo_pago` y `tipo_venta` a un conjunto cerrado y válido,
       evitando strings arbitrarios en la base de datos.
    3. `codigo_barras` y `referencia_pago` tienen restricción `unique=True` a nivel de
       base de datos: el código de barras no puede duplicarse entre productos, y el
       número de operación de Yape no puede reutilizarse (anti-fraude / anti-duplicidad).
    4. Se usan `CheckConstraint` para reforzar reglas de negocio básicas a nivel de BD
       (precios y stock no negativos), como una segunda capa de seguridad además de
       la validación que hará Pydantic en la capa de API (Módulo 2 en adelante).
    5. Todos los montos se guardan como `Numeric(10, 2)` en lugar de `Float`, para evitar
       errores de redondeo en operaciones con dinero (Soles, PEN).
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    CheckConstraint,
    Text,
    Boolean,
)
from sqlalchemy.orm import relationship

from database import Base


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------

class TipoDocumento(str, enum.Enum):
    """Tipo de documento de identidad/tributario del cliente (Perú)."""
    DNI = "DNI"
    RUC = "RUC"
    CE = "CE"


class MetodoPago(str, enum.Enum):
    """Métodos de pago soportados por el POS."""
    EFECTIVO = "EFECTIVO"
    YAPE = "YAPE"


class TipoVenta(str, enum.Enum):
    """Modalidad en la que se vendió un producto dentro de una línea de detalle."""
    UNIDAD = "UNIDAD"
    CAJA = "CAJA"


class RolUsuario(str, enum.Enum):
    """Rol del usuario dentro del sistema, para control de acceso básico."""
    ADMIN = "ADMIN"
    CAJERO = "CAJERO"


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------

class Producto(Base):
    """
    Catálogo de productos de la librería/papelería.

    Un producto puede venderse:
        - Solo por unidad (precio_venta_caja y unidades_por_caja quedan en NULL/1).
        - Por unidad Y por caja/paquete (ej: lapiceros que se venden sueltos o por caja
          de 12; cuadernos que se venden sueltos o en paquete de 50).

    El stock (`stock_unidades`) SIEMPRE se expresa en la unidad base más pequeña
    (ej: lapiceros individuales), nunca en cajas, para evitar ambigüedad.
    """
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    codigo_barras = Column(String(50), unique=True, index=True, nullable=True)
    nombre = Column(String(150), nullable=False, index=True)
    marca = Column(String(80), nullable=True, index=True)

    # --- Precios ---
    precio_compra = Column(Numeric(10, 2), nullable=False, default=0)
    precio_venta_unidad = Column(Numeric(10, 2), nullable=False)
    precio_venta_caja = Column(Numeric(10, 2), nullable=True)  # Opcional

    # --- Conversión unidad <-> caja ---
    # Ej: 12 (una caja de lapiceros trae 12 unidades) o 50 (un paquete de hojas trae 50).
    # Por defecto es 1 para productos que solo se venden por unidad.
    unidades_por_caja = Column(Integer, nullable=False, default=1)

    # --- Inventario ---
    # SIEMPRE en unidades base, sin importar si el producto también se vende por caja.
    stock_unidades = Column(Integer, nullable=False, default=0)

    # Baja lógica: si el producto tiene ventas registradas, no se puede
    # eliminar (rompería el historial); se marca como inactivo en su lugar.
    activo = Column(Boolean, nullable=False, default=True)

    fecha_registro = Column(DateTime, default=datetime.utcnow, nullable=False)

    # --- Relaciones ---
    detalles_venta = relationship(
        "DetalleVenta", back_populates="producto", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("precio_compra >= 0", name="ck_producto_precio_compra_no_negativo"),
        CheckConstraint("precio_venta_unidad >= 0", name="ck_producto_precio_unidad_no_negativo"),
        CheckConstraint(
            "precio_venta_caja IS NULL OR precio_venta_caja >= 0",
            name="ck_producto_precio_caja_no_negativo",
        ),
        CheckConstraint("unidades_por_caja >= 1", name="ck_producto_unidades_por_caja_valida"),
        CheckConstraint("stock_unidades >= 0", name="ck_producto_stock_no_negativo"),
    )

    def __repr__(self):
        return f"<Producto id={self.id} nombre='{self.nombre}' stock={self.stock_unidades}>"


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class Cliente(Base):
    """
    Registro opcional/básico de clientes. Una venta puede realizarse SIN cliente
    asociado (cliente_id nulo en Venta), pensado para ventas rápidas de mostrador.
    """
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    tipo_documento = Column(SAEnum(TipoDocumento), nullable=True)
    numero_documento = Column(String(20), nullable=True, unique=True, index=True)
    nombre_o_razon_social = Column(String(150), nullable=True)
    direccion = Column(String(255), nullable=True)

    fecha_registro = Column(DateTime, default=datetime.utcnow, nullable=False)

    # --- Relaciones ---
    ventas = relationship("Venta", back_populates="cliente")

    def __repr__(self):
        return f"<Cliente id={self.id} nombre='{self.nombre_o_razon_social}'>"


# ---------------------------------------------------------------------------
# Venta (cabecera)
# ---------------------------------------------------------------------------

class Venta(Base):
    """
    Cabecera de una transacción de venta. Contiene el total, el método de pago
    y los datos de conciliación de ese pago (vuelto para efectivo, referencia
    de operación para Yape).
    """
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Cliente opcional: se permite venta anónima / rápida de mostrador.
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)

    total = Column(Numeric(10, 2), nullable=False)

    metodo_pago = Column(SAEnum(MetodoPago), nullable=False)

    # Solo aplica para EFECTIVO. Para YAPE se deja en NULL.
    monto_recibido = Column(Numeric(10, 2), nullable=True)
    vuelto = Column(Numeric(10, 2), nullable=True)

    # Solo aplica para YAPE. Debe ser único para evitar fraude/duplicidad.
    # Para EFECTIVO se deja en NULL.
    referencia_pago = Column(String(50), nullable=True, unique=True, index=True)

    # --- Relaciones ---
    cliente = relationship("Cliente", back_populates="ventas")
    detalles = relationship(
        "DetalleVenta", back_populates="venta", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_venta_total_no_negativo"),
        CheckConstraint(
            "monto_recibido IS NULL OR monto_recibido >= 0",
            name="ck_venta_monto_recibido_no_negativo",
        ),
        CheckConstraint(
            "vuelto IS NULL OR vuelto >= 0",
            name="ck_venta_vuelto_no_negativo",
        ),
    )

    def __repr__(self):
        return f"<Venta id={self.id} total={self.total} metodo_pago={self.metodo_pago}>"


# ---------------------------------------------------------------------------
# DetalleVenta (líneas de la venta)
# ---------------------------------------------------------------------------

class DetalleVenta(Base):
    """
    Línea individual de una venta: un producto específico, vendido por UNIDAD o
    por CAJA, con la cantidad y el precio unitario efectivamente aplicado en ese
    momento (histórico, independiente de si el precio del producto cambia después).
    """
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)

    tipo_venta = Column(SAEnum(TipoVenta), nullable=False, default=TipoVenta.UNIDAD)

    # Cantidad de unidades o de cajas vendidas, según `tipo_venta`.
    cantidad = Column(Integer, nullable=False)

    # Precio unitario (por unidad o por caja, según tipo_venta) vigente al momento
    # de la venta. Se guarda como snapshot histórico, no se recalcula desde Producto.
    precio_unitario_aplicado = Column(Numeric(10, 2), nullable=False)

    # subtotal = cantidad * precio_unitario_aplicado
    subtotal = Column(Numeric(10, 2), nullable=False)

    # --- Relaciones ---
    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles_venta")

    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_detalle_cantidad_positiva"),
        CheckConstraint("precio_unitario_aplicado >= 0", name="ck_detalle_precio_no_negativo"),
        CheckConstraint("subtotal >= 0", name="ck_detalle_subtotal_no_negativo"),
    )

    def __repr__(self):
        return (
            f"<DetalleVenta id={self.id} producto_id={self.producto_id} "
            f"tipo={self.tipo_venta} cantidad={self.cantidad}>"
        )


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------

class Usuario(Base):
    """
    Cuenta de acceso al sistema (login). Cada venta, en un futuro módulo,
    podría además registrar qué usuario la realizó (auditoría) -- por ahora
    esta tabla solo cubre el control de acceso: quién puede entrar al
    sistema y con qué rol.

    La contraseña NUNCA se guarda en texto plano: `password_hash` contiene
    el resultado de `security.hash_password()` (sal + hash PBKDF2-HMAC-SHA256).
    """
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    nombre_completo = Column(String(150), nullable=False)
    rol = Column(SAEnum(RolUsuario), nullable=False, default=RolUsuario.CAJERO)

    # Permite desactivar el acceso de un usuario (ej. un empleado que ya no
    # trabaja en la papelería) sin tener que borrar su historial.
    activo = Column(Boolean, nullable=False, default=True)

    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Usuario id={self.id} username='{self.username}' rol={self.rol}>"

