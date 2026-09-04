"""
views/producto_dialog.py
-------------------------
Ventana modal (CTkToplevel) para crear o editar un producto. Un mismo
diálogo sirve para ambos casos:
    - Modo CREAR:  se abre con `producto=None`, todos los campos vacíos.
    - Modo EDITAR: se abre con `producto=<dict devuelto por la API>`,
                    los campos vienen pre-llenados con sus valores actuales.

El diálogo NO decide nada de negocio por su cuenta: arma el payload y se lo
pasa a `ApiClient`. Toda regla de negocio (unicidad de código de barras,
coherencia caja/unidades, etc.) la valida el backend; aquí solo mostramos
el mensaje de error que el backend devuelva si algo falla.
"""

from decimal import Decimal, InvalidOperation
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

from api_client import ApiClient, ApiError


class ProductoDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        api: ApiClient,
        on_guardado: Callable[[], None],
        producto: Optional[dict] = None,
    ):
        super().__init__(master)
        self.api = api
        self.on_guardado = on_guardado
        self.producto = producto  # None = crear, dict = editar
        self.es_edicion = producto is not None

        self.title("Editar producto" if self.es_edicion else "Nuevo producto")
        self.geometry("420x560")
        self.resizable(False, False)

        # Modal: bloquea interacción con la ventana principal mientras está abierto.
        self.transient(master)
        self.grab_set()

        self._construir_formulario()
        if self.es_edicion:
            self._precargar_valores()

        self.after(50, lambda: self.campo_nombre.focus())

    # -----------------------------------------------------------------
    # Construcción del formulario
    # -----------------------------------------------------------------

    def _construir_formulario(self):
        self.grid_columnconfigure(0, weight=1)

        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.grid(row=0, column=0, padx=24, pady=20, sticky="nsew")
        contenedor.grid_columnconfigure(0, weight=1)

        def etiqueta(texto, fila, requerido=False):
            texto_final = f"{texto} *" if requerido else texto
            ctk.CTkLabel(contenedor, text=texto_final, anchor="w").grid(
                row=fila, column=0, sticky="w", pady=(10, 2)
            )

        etiqueta("Código de barras", 0)
        self.campo_codigo_barras = ctk.CTkEntry(contenedor, placeholder_text="Opcional")
        self.campo_codigo_barras.grid(row=1, column=0, sticky="ew")

        etiqueta("Nombre del producto", 2, requerido=True)
        self.campo_nombre = ctk.CTkEntry(contenedor)
        self.campo_nombre.grid(row=3, column=0, sticky="ew")

        etiqueta("Marca", 4)
        self.campo_marca = ctk.CTkEntry(contenedor, placeholder_text="Opcional")
        self.campo_marca.grid(row=5, column=0, sticky="ew")

        fila_precios = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_precios.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        fila_precios.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(fila_precios, text="Precio de compra (S/)", anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(fila_precios, text="Precio venta x unidad (S/) *", anchor="w").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        self.campo_precio_compra = ctk.CTkEntry(fila_precios, placeholder_text="0.00")
        self.campo_precio_compra.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.campo_precio_venta_unidad = ctk.CTkEntry(fila_precios, placeholder_text="0.00")
        self.campo_precio_venta_unidad.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(2, 0))

        # --- Bloque "también se vende por caja" ---
        self.switch_vende_por_caja = ctk.CTkSwitch(
            contenedor,
            text="También se vende por caja / paquete",
            command=self._alternar_campos_caja,
        )
        self.switch_vende_por_caja.grid(row=7, column=0, sticky="w", pady=(18, 0))

        fila_caja = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_caja.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        fila_caja.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(fila_caja, text="Precio venta x caja (S/)", anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(fila_caja, text="Unidades por caja", anchor="w").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        self.campo_precio_venta_caja = ctk.CTkEntry(
            fila_caja, placeholder_text="0.00", state="disabled"
        )
        self.campo_precio_venta_caja.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.campo_unidades_por_caja = ctk.CTkEntry(
            fila_caja, placeholder_text="12", state="disabled"
        )
        self.campo_unidades_por_caja.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(2, 0))

        etiqueta("Stock (en unidades) *", 9)
        self.campo_stock = ctk.CTkEntry(contenedor, placeholder_text="0")
        self.campo_stock.grid(row=10, column=0, sticky="ew")

        if self.es_edicion:
            nota = (
                "Nota: este stock reemplaza directamente al actual. Úsalo para "
                "ajustes por compra a proveedor o conteo físico."
            )
            ctk.CTkLabel(
                contenedor,
                text=nota,
                anchor="w",
                justify="left",
                wraplength=360,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
            ).grid(row=11, column=0, sticky="w", pady=(6, 0))

        # --- Botones ---
        fila_botones = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_botones.grid(row=12, column=0, sticky="ew", pady=(24, 0))
        fila_botones.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            fila_botones, text="Cancelar", fg_color="gray", command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            fila_botones, text="Guardar", command=self._guardar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _alternar_campos_caja(self):
        activo = self.switch_vende_por_caja.get() == 1
        estado = "normal" if activo else "disabled"
        self.campo_precio_venta_caja.configure(state=estado)
        self.campo_unidades_por_caja.configure(state=estado)
        if not activo:
            self.campo_precio_venta_caja.delete(0, "end")
            self.campo_unidades_por_caja.delete(0, "end")

    # -----------------------------------------------------------------
    # Precarga de valores (modo edición)
    # -----------------------------------------------------------------

    def _precargar_valores(self):
        p = self.producto
        self.campo_codigo_barras.insert(0, p.get("codigo_barras") or "")
        self.campo_nombre.insert(0, p.get("nombre") or "")
        self.campo_marca.insert(0, p.get("marca") or "")
        self.campo_precio_compra.insert(0, str(p.get("precio_compra", "0")))
        self.campo_precio_venta_unidad.insert(0, str(p.get("precio_venta_unidad", "0")))
        self.campo_stock.insert(0, str(p.get("stock_unidades", "0")))

        if p.get("precio_venta_caja") is not None:
            self.switch_vende_por_caja.select()
            self._alternar_campos_caja()
            self.campo_precio_venta_caja.insert(0, str(p["precio_venta_caja"]))
            self.campo_unidades_por_caja.insert(0, str(p.get("unidades_por_caja", "")))

    # -----------------------------------------------------------------
    # Guardar (crear o actualizar, según el modo)
    # -----------------------------------------------------------------

    def _leer_decimal(self, entry: ctk.CTkEntry, nombre_campo: str, requerido: bool) -> Optional[Decimal]:
        texto = entry.get().strip()
        if not texto:
            if requerido:
                raise ValueError(f"El campo '{nombre_campo}' es obligatorio.")
            return None
        try:
            return Decimal(texto.replace(",", "."))
        except InvalidOperation:
            raise ValueError(f"El campo '{nombre_campo}' debe ser un número válido (ej: 12.50).")

    def _leer_entero(self, entry: ctk.CTkEntry, nombre_campo: str, requerido: bool, por_defecto=None):
        texto = entry.get().strip()
        if not texto:
            if requerido:
                raise ValueError(f"El campo '{nombre_campo}' es obligatorio.")
            return por_defecto
        try:
            return int(texto)
        except ValueError:
            raise ValueError(f"El campo '{nombre_campo}' debe ser un número entero (ej: 12).")

    def _guardar(self):
        try:
            nombre = self.campo_nombre.get().strip()
            if not nombre:
                raise ValueError("El nombre del producto es obligatorio.")

            vende_por_caja = self.switch_vende_por_caja.get() == 1

            payload = {
                "codigo_barras": self.campo_codigo_barras.get().strip() or None,
                "nombre": nombre,
                "marca": self.campo_marca.get().strip() or None,
                "precio_compra": str(
                    self._leer_decimal(self.campo_precio_compra, "Precio de compra", requerido=False)
                    or Decimal("0")
                ),
                "precio_venta_unidad": str(
                    self._leer_decimal(
                        self.campo_precio_venta_unidad, "Precio venta x unidad", requerido=True
                    )
                ),
                "stock_unidades": self._leer_entero(
                    self.campo_stock, "Stock", requerido=True
                ),
            }

            if vende_por_caja:
                precio_caja = self._leer_decimal(
                    self.campo_precio_venta_caja, "Precio venta x caja", requerido=True
                )
                unidades_caja = self._leer_entero(
                    self.campo_unidades_por_caja, "Unidades por caja", requerido=True
                )
                payload["precio_venta_caja"] = str(precio_caja)
                payload["unidades_por_caja"] = unidades_caja
            else:
                payload["precio_venta_caja"] = None
                payload["unidades_por_caja"] = 1

        except ValueError as exc:
            messagebox.showerror("Datos inválidos", str(exc), parent=self)
            return

        try:
            if self.es_edicion:
                self.api.actualizar_producto(self.producto["id"], payload)
            else:
                self.api.crear_producto(payload)
        except ApiError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return

        messagebox.showinfo(
            "Listo",
            "Producto actualizado correctamente." if self.es_edicion else "Producto creado correctamente.",
            parent=self,
        )
        self.on_guardado()
        self.destroy()
