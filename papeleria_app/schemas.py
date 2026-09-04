"""
schemas.py
----------
Esquemas Pydantic (capa de validación de entrada/salida de la API) para el
Sistema POS de Librería/Papelería.

Este módulo se irá ampliando en cada bloque del plan de desarrollo
(Módulo 2: Producto, Módulo 3: Cliente, Módulo 4: Venta/DetalleVenta).
Por ahora contiene únicamente los esquemas de Producto.

Convención usada en todo el archivo:
    - `*Base`    -> campos compartidos entre creación y lectura.
    - `*Create`  -> lo que el cliente envía al crear un recurso (POST).
    - `*Update`  -> lo que el cliente envía al actualizar (PUT/PATCH). Todos los
                    campos son opcionales para permitir actualizaciones parciales.
    - `*Out`     -> lo que la API devuelve (incluye campos generados por la BD,
                    como `id` y `fecha_registro`).
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------

class ProductoBase(BaseModel):
    """Campos comunes a la creación y a la salida de un producto."""

    codigo_barras: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Código de barras del producto. Opcional, pero único si se envía.",
    )
    nombre: str = Field(..., min_length=1, max_length=150, description="Nombre del producto.")
    marca: Optional[str] = Field(default=None, max_length=80)

    precio_compra: Decimal = Field(
        default=Decimal("0"), ge=0, description="Costo de adquisición del producto."
    )
    precio_venta_unidad: Decimal = Field(
        ..., gt=0, description="Precio de venta al público, por unidad."
    )
    precio_venta_caja: Optional[Decimal] = Field(
        default=None, gt=0, description="Precio de venta al público, por caja/paquete (opcional)."
    )
    unidades_por_caja: int = Field(
        default=1, ge=1, description="Cantidad de unidades base que trae una caja/paquete."
    )
    stock_unidades: int = Field(
        default=0, ge=0, description="Stock actual, expresado siempre en unidades base."
    )

    @field_validator("codigo_barras", "marca")
    @classmethod
    def _vacio_a_none(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza cadenas vacías o solo-espacios a None, para no romper el
        índice único de `codigo_barras` con strings vacíos duplicados."""
        if v is not None and v.strip() == "":
            return None
        return v.strip() if v else v

    @model_validator(mode="after")
    def _validar_coherencia_caja(self) -> "ProductoBase":
        """
        Regla de negocio: si el producto define un precio de venta por caja,
        debe indicarse cuántas unidades trae esa caja (debe ser > 1; si fuera 1
        no tendría sentido diferenciarlo de la venta por unidad).
        """
        if self.precio_venta_caja is not None and self.unidades_por_caja <= 1:
            raise ValueError(
                "Si se define 'precio_venta_caja', 'unidades_por_caja' debe ser mayor a 1."
            )
        return self


class ProductoCreate(ProductoBase):
    """Payload esperado en POST /productos/."""
    pass


class ProductoUpdate(BaseModel):
    """
    Payload esperado en PUT /productos/{id}.
    Todos los campos son opcionales: solo se actualizan los que el cliente envíe.
    """
    codigo_barras: Optional[str] = Field(default=None, max_length=50)
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=150)
    marca: Optional[str] = Field(default=None, max_length=80)
    precio_compra: Optional[Decimal] = Field(default=None, ge=0)
    precio_venta_unidad: Optional[Decimal] = Field(default=None, gt=0)
    precio_venta_caja: Optional[Decimal] = Field(default=None, gt=0)
    unidades_por_caja: Optional[int] = Field(default=None, ge=1)
    stock_unidades: Optional[int] = Field(default=None, ge=0)
    activo: Optional[bool] = Field(default=None)

    @field_validator("codigo_barras", "marca", "nombre")
    @classmethod
    def _vacio_a_none(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == "":
            return None
        return v.strip() if v else v


class ProductoOut(ProductoBase):
    """Lo que la API devuelve al consultar/crear un producto."""
    model_config = ConfigDict(from_attributes=True)  # permite construir desde el objeto ORM

    id: int
    activo: bool = True
    fecha_registro: datetime


class ProductoListaOut(BaseModel):
    """Envoltura estándar para listados paginados de productos."""
    model_config = ConfigDict(from_attributes=True)

    total: int
    items: list[ProductoOut]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class ClienteBase(BaseModel):
    """Campos comunes a la creación y a la salida de un cliente."""

    tipo_documento: Optional[Literal["DNI", "RUC", "CE"]] = Field(
        default=None, description="Tipo de documento: DNI, RUC o CE. Opcional (registro básico)."
    )
    numero_documento: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Número de DNI (8 dígitos) o RUC (11 dígitos). Opcional, pero único si se envía.",
    )
    nombre_o_razon_social: Optional[str] = Field(default=None, max_length=150)
    direccion: Optional[str] = Field(default=None, max_length=255)

    @field_validator("numero_documento", "nombre_o_razon_social", "direccion")
    @classmethod
    def _vacio_a_none(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza cadenas vacías/solo-espacios a None (evita choques en el
        índice único de `numero_documento` por strings vacíos duplicados)."""
        if v is not None and v.strip() == "":
            return None
        return v.strip() if v else v

    @model_validator(mode="after")
    def _validar_coherencia_documento(self) -> "ClienteBase":
        """
        Reglas de negocio para el registro "opcional o básico" de clientes:
            - Si se envía `tipo_documento`, también debe enviarse `numero_documento`
              (y viceversa): no tiene sentido un tipo de documento sin número, ni un
              número de documento sin saber si es DNI o RUC.
            - Si el tipo es DNI, el número debe tener exactamente 8 dígitos.
            - Si el tipo es RUC, el número debe tener exactamente 11 dígitos.
        Todo el bloque de documento puede omitirse por completo (venta rápida,
        cliente anónimo de mostrador).
        """
        if self.tipo_documento is not None and self.numero_documento is None:
            raise ValueError(
                "Si indicas 'tipo_documento' debes indicar también 'numero_documento'."
            )
        if self.numero_documento is not None and self.tipo_documento is None:
            raise ValueError(
                "Si indicas 'numero_documento' debes indicar también 'tipo_documento' (DNI o RUC)."
            )
        if self.tipo_documento == "DNI" and self.numero_documento is not None:
            if not (self.numero_documento.isdigit() and len(self.numero_documento) == 8):
                raise ValueError("El DNI debe tener exactamente 8 dígitos numéricos.")
        if self.tipo_documento == "RUC" and self.numero_documento is not None:
            if not (self.numero_documento.isdigit() and len(self.numero_documento) == 11):
                raise ValueError("El RUC debe tener exactamente 11 dígitos numéricos.")
        if self.tipo_documento == "CE" and self.numero_documento is not None:
            # El Carnet de Extranjería no tiene un largo único estandarizado en
            # la práctica; solo se descartan valores evidentemente inválidos.
            valor = self.numero_documento.strip()
            if not (6 <= len(valor) <= 12 and valor.isalnum()):
                raise ValueError(
                    "El Carnet de Extranjería debe tener entre 6 y 12 caracteres alfanuméricos."
                )
        return self


class ClienteCreate(ClienteBase):
    """Payload esperado en POST /clientes/."""
    pass


class ClienteOut(ClienteBase):
    """Lo que la API devuelve al consultar/crear un cliente."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_registro: datetime


# ---------------------------------------------------------------------------
# Venta / DetalleVenta
# ---------------------------------------------------------------------------
#
# DECISIÓN DE DISEÑO IMPORTANTE: el cliente de la API (la app de escritorio)
# NUNCA envía precios ni el total de la venta. Solo envía QUÉ se vendió
# (producto_id, tipo_venta, cantidad) y CÓMO se pagó. El precio unitario, el
# subtotal de cada línea y el total de la venta los calcula siempre el
# servidor a partir del precio vigente en el catálogo (`Producto`). Esto
# evita que alguien manipule el request para pagar menos de lo que
# corresponde, y es la práctica estándar en cualquier motor de ventas real.

class DetalleVentaCreate(BaseModel):
    """
    Una línea de venta tal como la envía el cliente: solo identifica el
    producto, la modalidad (UNIDAD o CAJA) y la cantidad. El precio se
    resuelve del lado del servidor.
    """
    producto_id: int = Field(..., gt=0)
    tipo_venta: Literal["UNIDAD", "CAJA"]
    cantidad: int = Field(..., gt=0, description="Cantidad de unidades o de cajas, según 'tipo_venta'.")


class DetalleVentaOut(BaseModel):
    """Línea de venta ya resuelta, tal como se guardó y se devuelve al cliente."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    producto_nombre: Optional[str] = None
    tipo_venta: str
    cantidad: int
    precio_unitario_aplicado: Decimal
    subtotal: Decimal


class VentaCreate(BaseModel):
    """
    Payload esperado en POST /ventas/.

    Reglas de pago (validadas aquí, a nivel de "forma"; la validación de que
    `monto_recibido` alcance para cubrir el `total` se hace en el router,
    porque el total se calcula recién ahí a partir de los productos):
        - EFECTIVO: requiere 'monto_recibido'; no debe traer 'referencia_pago'.
        - YAPE: requiere 'referencia_pago' (no vacío); no debe traer 'monto_recibido'.
    """
    cliente_id: Optional[int] = Field(default=None, gt=0)
    metodo_pago: Literal["EFECTIVO", "YAPE"]
    monto_recibido: Optional[Decimal] = Field(default=None, ge=0)
    referencia_pago: Optional[str] = Field(default=None, max_length=50)
    detalles: list[DetalleVentaCreate] = Field(..., min_length=1)

    @field_validator("referencia_pago")
    @classmethod
    def _normalizar_referencia(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == "":
            return None
        return v.strip() if v else v

    @model_validator(mode="after")
    def _validar_forma_del_pago(self) -> "VentaCreate":
        if self.metodo_pago == "EFECTIVO":
            if self.monto_recibido is None:
                raise ValueError("Para pago en EFECTIVO debes indicar 'monto_recibido'.")
            if self.referencia_pago is not None:
                raise ValueError("'referencia_pago' no aplica para pagos en EFECTIVO.")
        elif self.metodo_pago == "YAPE":
            if self.monto_recibido is not None:
                raise ValueError("'monto_recibido' no aplica para pagos con YAPE (no hay vuelto).")
        return self


class VentaOut(BaseModel):
    """Lo que la API devuelve tras registrar (o consultar) una venta."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: datetime
    cliente_id: Optional[int]
    total: Decimal
    metodo_pago: str
    monto_recibido: Optional[Decimal]
    vuelto: Optional[Decimal]
    referencia_pago: Optional[str]
    detalles: list[DetalleVentaOut]


# ---------------------------------------------------------------------------
# Autenticación / Usuarios
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Payload esperado en POST /auth/login."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UsuarioOut(BaseModel):
    """
    Datos públicos de un usuario. Nunca incluye `password_hash` -- ese
    campo jamás sale del backend, ni siquiera hasheado.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre_completo: str
    rol: str
    activo: bool
    fecha_creacion: datetime


class LoginResponse(BaseModel):
    """Lo que devuelve un login exitoso: el token de sesión y los datos del usuario."""
    token: str
    usuario: UsuarioOut


class UsuarioCreate(BaseModel):
    """Payload esperado en POST /usuarios/ (solo accesible para administradores)."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    nombre_completo: str = Field(..., min_length=1, max_length=150)
    rol: Literal["ADMIN", "CAJERO"] = "CAJERO"

    @field_validator("username")
    @classmethod
    def _username_sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if " " in v:
            raise ValueError("El nombre de usuario no puede contener espacios.")
        return v.lower()


class RegistroUsuarioRequest(BaseModel):
    """
    Payload esperado en POST /auth/registro -- el registro público desde la
    pantalla de login (sin necesitar sesión iniciada).

    Reglas:
        - Cualquiera puede crearse una cuenta de rol CAJERO libremente.
        - Crear una cuenta ADMIN requiere las credenciales de un
          administrador ya existente (`admin_username`/`admin_password`),
          EXCEPTO si todavía no existe ningún usuario en el sistema (el
          primer usuario, típicamente el dueño del negocio configurando la
          app por primera vez).
    """
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    confirmar_password: str = Field(..., min_length=6, max_length=100)
    nombre_completo: str = Field(..., min_length=1, max_length=150)
    rol: Literal["ADMIN", "CAJERO"] = "CAJERO"

    admin_username: Optional[str] = None
    admin_password: Optional[str] = None

    @field_validator("username")
    @classmethod
    def _username_sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if " " in v:
            raise ValueError("El nombre de usuario no puede contener espacios.")
        return v.lower()

    @model_validator(mode="after")
    def _validar_confirmacion(self) -> "RegistroUsuarioRequest":
        if self.password != self.confirmar_password:
            raise ValueError("Las contraseñas no coinciden.")
        return self


# ---------------------------------------------------------------------------
# Importación de productos desde Excel
# ---------------------------------------------------------------------------

class FilaImportadaOut(BaseModel):
    fila_excel: int
    marca: Optional[str] = None
    nombre: Optional[str] = None
    codigo_barras: Optional[str] = None
    precio_compra: Optional[str] = None
    precio_venta_unidad: Optional[str] = None
    precio_venta_caja: Optional[str] = None
    unidades_por_caja: int = 1
    stock_unidades: int = 0
    error: Optional[str] = None
    advertencia: Optional[str] = None
    accion: Optional[Literal["crear", "actualizar", "omitir"]] = None
    producto_existente_id: Optional[int] = None


class VistaPreviaImportacionOut(BaseModel):
    total: int
    nuevos: int
    existentes: int
    con_errores: int
    filas: list[FilaImportadaOut]
    error_general: Optional[str] = None


class ConfirmarImportacionRequest(BaseModel):
    modo: Literal["agregar_nuevos", "actualizar_y_crear"]
    actualizar_stock: bool = False
    filas: list[FilaImportadaOut]


class ConfirmarImportacionOut(BaseModel):
    nuevos: int
    actualizados: int
    omitidos: int


class ReemplazarTodoRequest(BaseModel):
    filas: list[FilaImportadaOut]
    confirmacion: str


class ReemplazarTodoOut(BaseModel):
    eliminados: int
    conservados_por_tener_ventas: int
    nuevos: int


class EliminarProductosRequest(BaseModel):
    ids: list[int]


class EliminarProductosOut(BaseModel):
    eliminados: int
    no_eliminables: list[dict]
