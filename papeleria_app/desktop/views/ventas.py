"""
views/ventas.py
----------------
Pantalla de Ventas / Punto de Venta (Módulo 8) — la más importante de la app.

Flujo de uso pensado para el mostrador:
    1. El vendedor busca un producto (por nombre o código de barras), elige
       si lo vende por UNIDAD o por CAJA, indica la cantidad, y lo agrega
       al carrito. Repite para cada producto.
    2. Opcionalmente busca al cliente por DNI/RUC (si no, la venta queda
       anónima -- venta rápida de mostrador).
    3. Elige el método de pago:
           - EFECTIVO: ingresa el monto recibido; el vuelto se calcula al
             confirmar la venta (el backend es quien calcula el vuelto real).
           - YAPE: ingresa el número de operación.
    4. Presiona "Registrar venta". Si todo es válido, el backend registra la
       venta de forma atómica (Módulo 4 de la API) y descuenta el stock.

DECISIÓN DE DISEÑO IMPORTANTE (coherente con el backend): los precios y el
total que se muestran en el carrito ANTES de confirmar son solo
"referenciales" (se calculan aquí con los precios que trajo la búsqueda de
productos, para que el vendedor vea cuánto va costando). El total, el
vuelto y los precios DEFINITIVOS los calcula siempre el servidor al
confirmar la venta -- la interfaz nunca le "dice" al backend cuánto cobrar.
"""

from decimal import Decimal, InvalidOperation
from tkinter import messagebox, ttk

import customtkinter as ctk

from api_client import ApiClient, ApiError
from views.resumen_financiero_dialog import ResumenFinancieroDialog


class VentasView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api

        self.carrito: list[dict] = []
        self.producto_seleccionado: dict | None = None

        # NOTA TÉCNICA: VentasView en sí es un CTkFrame normal (igual que las
        # demás pantallas), para que el intercambio de vistas con tkraise()
        # en app.py funcione de forma idéntica y predecible en cualquier
        # versión de CustomTkinter. El contenido con scroll vive DENTRO,
        # en `self.scroll`, en vez de que la vista completa sea un
        # CTkScrollableFrame (que en algunas versiones de CustomTkinter no
        # se comporta igual que un CTkFrame normal al apilarse con tkraise).
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        self._crear_encabezado()
        self._crear_seccion_buscar_producto()
        self._crear_seccion_carrito()
        self._crear_seccion_pago()
        self._crear_boton_registrar()

    # -----------------------------------------------------------------
    # Encabezado
    # -----------------------------------------------------------------

    def _crear_encabezado(self):
        encabezado = ctk.CTkFrame(self.scroll, fg_color="transparent")
        encabezado.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 16))
        encabezado.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            encabezado, text="💰 Ventas (POS)", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            encabezado, text="📊 Resumen financiero", fg_color="gray", width=170,
            command=self._abrir_resumen_financiero,
        ).grid(row=0, column=1, sticky="e")

    def _abrir_resumen_financiero(self):
        ResumenFinancieroDialog(self, api=self.api)

    # -----------------------------------------------------------------
    # Sección 1: buscar y agregar producto
    # -----------------------------------------------------------------

    def _crear_seccion_buscar_producto(self):
        marco = ctk.CTkFrame(self.scroll, corner_radius=12)
        marco.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 16))
        marco.grid_columnconfigure(0, weight=1)


        ctk.CTkLabel(
            marco, text="1. Agregar productos", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 8))

        self.campo_buscar_producto = ctk.CTkEntry(
            marco, placeholder_text="Buscar producto por nombre o código de barras..."
        )
        self.campo_buscar_producto.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 10))
        self.campo_buscar_producto.bind("<Return>", lambda _evt: self._buscar_producto())

        ctk.CTkButton(
            marco, text="Buscar", width=90, command=self._buscar_producto
        ).grid(row=1, column=1, padx=(0, 16), pady=(0, 10))

        # --- Resultados de búsqueda ---
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Treeview", rowheight=26, font=("Segoe UI", 10))

        cols_resultado = ("nombre", "marca", "precio_unidad")
        self.tabla_resultados = ttk.Treeview(
            marco, columns=cols_resultado, show="headings", height=4, selectmode="browse"
        )
        encabezados = {
            "nombre": "Producto",
            "marca": "Marca",
            "precio_unidad": "Precio x unidad",
        }
        anchos = {"nombre": 260, "marca": 140, "precio_unidad": 130}
        for col in cols_resultado:
            self.tabla_resultados.heading(col, text=encabezados[col])
            self.tabla_resultados.column(
                col, width=anchos[col], anchor="center" if col not in ("nombre", "marca") else "w"
            )
        self.tabla_resultados.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16)
        self.tabla_resultados.bind("<<TreeviewSelect>>", self._al_seleccionar_producto)

        # --- Panel para agregar el producto seleccionado ---
        panel_agregar = ctk.CTkFrame(marco, fg_color="transparent")
        panel_agregar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(10, 16))
        panel_agregar.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(panel_agregar, text="Cantidad:").grid(row=0, column=0, padx=(0, 6))
        self.campo_cantidad = ctk.CTkEntry(panel_agregar, width=70, placeholder_text="1")
        self.campo_cantidad.grid(row=0, column=1, padx=(0, 16))

        ctk.CTkLabel(panel_agregar, text="Modalidad:").grid(row=0, column=2, padx=(0, 6))
        self.combo_tipo_venta = ctk.CTkComboBox(
            panel_agregar, values=["UNIDAD"], width=110, state="readonly"
        )
        self.combo_tipo_venta.grid(row=0, column=3, sticky="w")

        self.boton_agregar_carrito = ctk.CTkButton(
            panel_agregar, text="➕ Agregar al carrito", command=self._agregar_al_carrito
        )
        self.boton_agregar_carrito.grid(row=0, column=4, sticky="e", padx=(16, 0))

        self.label_producto_seleccionado = ctk.CTkLabel(
            marco, text="Ningún producto seleccionado.", text_color=("gray30", "gray70")
        )
        self.label_producto_seleccionado.grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12)
        )

    def _buscar_producto(self):
        texto = self.campo_buscar_producto.get().strip()
        if not texto:
            return
        try:
            if texto.isdigit() and len(texto) >= 6:
                resultado = self.api.buscar_productos(codigo_barras=texto)
                if not resultado["items"]:
                    resultado = self.api.buscar_productos(q=texto)
            else:
                resultado = self.api.buscar_productos(q=texto)
        except ApiError as exc:
            messagebox.showerror("Error al buscar", str(exc), parent=self)
            return

        self.tabla_resultados.delete(*self.tabla_resultados.get_children())
        self._productos_encontrados = {p["id"]: p for p in resultado["items"]}
        for p in resultado["items"]:
            precio_caja = f"S/ {p['precio_venta_caja']}" if p.get("precio_venta_caja") is not None else "—"
            self.tabla_resultados.insert(
                "",
                "end",
                iid=str(p["id"]),
                values=(p["nombre"], p.get("marca") or "—", f"S/ {p['precio_venta_unidad']}"),
            )

        if not resultado["items"]:
            messagebox.showinfo(
                "Sin resultados", f"No se encontraron productos para '{texto}'.", parent=self
            )

    def _al_seleccionar_producto(self, _evento=None):
        seleccion = self.tabla_resultados.selection()
        if not seleccion:
            return
        producto_id = int(seleccion[0])
        self.producto_seleccionado = self._productos_encontrados.get(producto_id)
        if not self.producto_seleccionado:
            return

        if self.producto_seleccionado.get("precio_venta_caja") is not None:
            self.combo_tipo_venta.configure(values=["UNIDAD", "CAJA"])
        else:
            self.combo_tipo_venta.configure(values=["UNIDAD"])
        self.combo_tipo_venta.set("UNIDAD")

        self.label_producto_seleccionado.configure(
            text=(
                f"Seleccionado: {self.producto_seleccionado['nombre']} "
                f"(stock disponible: {self.producto_seleccionado['stock_unidades']} unidades)"
            )
        )

    def _agregar_al_carrito(self):
        if self.producto_seleccionado is None:
            messagebox.showwarning(
                "Ningún producto seleccionado",
                "Busca un producto y selecciónalo de la lista de resultados antes de agregarlo.",
                parent=self,
            )
            return

        texto_cantidad = self.campo_cantidad.get().strip() or "1"
        try:
            cantidad = int(texto_cantidad)
            if cantidad <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Cantidad inválida", "La cantidad debe ser un número entero mayor a 0.", parent=self
            )
            return

        tipo_venta = self.combo_tipo_venta.get()
        producto = self.producto_seleccionado

        precio_unitario = (
            Decimal(str(producto["precio_venta_caja"]))
            if tipo_venta == "CAJA"
            else Decimal(str(producto["precio_venta_unidad"]))
        )
        subtotal = (precio_unitario * cantidad).quantize(Decimal("0.01"))

        self.carrito.append(
            {
                "producto_id": producto["id"],
                "nombre": producto["nombre"],
                "tipo_venta": tipo_venta,
                "cantidad": cantidad,
                "precio_unitario_referencial": precio_unitario,
                "subtotal_referencial": subtotal,
            }
        )
        self._refrescar_carrito()

        # Limpiar selección para el siguiente producto.
        self.campo_cantidad.delete(0, "end")
        self.campo_buscar_producto.delete(0, "end")
        self.tabla_resultados.delete(*self.tabla_resultados.get_children())
        self.producto_seleccionado = None
        self.label_producto_seleccionado.configure(text="Ningún producto seleccionado.")

    # -----------------------------------------------------------------
    # Sección 2: carrito
    # -----------------------------------------------------------------

    def _crear_seccion_carrito(self):
        marco = ctk.CTkFrame(self.scroll, corner_radius=12)
        marco.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        marco.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            marco, text="2. Carrito de venta", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        cols = ("producto", "tipo", "cantidad", "precio_unit", "subtotal")
        self.tabla_carrito = ttk.Treeview(
            marco, columns=cols, show="headings", height=5, selectmode="browse"
        )
        encabezados = {
            "producto": "Producto",
            "tipo": "Modalidad",
            "cantidad": "Cantidad",
            "precio_unit": "P. unitario (ref.)",
            "subtotal": "Subtotal (ref.)",
        }
        anchos = {"producto": 260, "tipo": 90, "cantidad": 80, "precio_unit": 120, "subtotal": 120}
        for col in cols:
            self.tabla_carrito.heading(col, text=encabezados[col])
            self.tabla_carrito.column(col, width=anchos[col], anchor="center" if col != "producto" else "w")
        self.tabla_carrito.grid(row=1, column=0, sticky="ew", padx=16)

        pie = ctk.CTkFrame(marco, fg_color="transparent")
        pie.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 16))
        pie.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            pie, text="🗑️ Quitar línea seleccionada", fg_color="gray", command=self._quitar_del_carrito
        ).grid(row=0, column=0, sticky="w")

        self.label_total = ctk.CTkLabel(
            pie, text="Total: S/ 0.00", font=ctk.CTkFont(size=16, weight="bold")
        )
        self.label_total.grid(row=0, column=1, sticky="e")

    def _refrescar_carrito(self):
        self.tabla_carrito.delete(*self.tabla_carrito.get_children())
        total = Decimal("0")
        for idx, linea in enumerate(self.carrito):
            self.tabla_carrito.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    linea["nombre"],
                    linea["tipo_venta"],
                    linea["cantidad"],
                    f"S/ {linea['precio_unitario_referencial']}",
                    f"S/ {linea['subtotal_referencial']}",
                ),
            )
            total += linea["subtotal_referencial"]
        self.label_total.configure(text=f"Total: S/ {total.quantize(Decimal('0.01'))}")

    def _quitar_del_carrito(self):
        seleccion = self.tabla_carrito.selection()
        if not seleccion:
            messagebox.showwarning(
                "Ninguna línea seleccionada",
                "Selecciona una línea del carrito para quitarla.",
                parent=self,
            )
            return
        idx = int(seleccion[0])
        del self.carrito[idx]
        self._refrescar_carrito()

    # -----------------------------------------------------------------
    # Sección 3: pago
    # -----------------------------------------------------------------

    def _crear_seccion_pago(self):
        marco = ctk.CTkFrame(self.scroll, corner_radius=12)
        marco.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 16))
        marco.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            marco, text="4. Método de pago", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self.segmento_metodo_pago = ctk.CTkSegmentedButton(
            marco, values=["EFECTIVO", "YAPE"], command=self._alternar_campos_pago
        )
        self.segmento_metodo_pago.set("EFECTIVO")
        self.segmento_metodo_pago.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        # --- Sub-panel EFECTIVO ---
        self.panel_efectivo = ctk.CTkFrame(marco, fg_color="transparent")
        self.panel_efectivo.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        ctk.CTkLabel(self.panel_efectivo, text="Monto recibido (S/):").pack(side="left", padx=(0, 8))
        self.campo_monto_recibido = ctk.CTkEntry(self.panel_efectivo, width=140, placeholder_text="0.00")
        self.campo_monto_recibido.pack(side="left")

        # --- Sub-panel YAPE (opcional: nº de operación, ya no es obligatorio) ---
        self.panel_yape = ctk.CTkFrame(marco, fg_color="transparent")
        ctk.CTkLabel(self.panel_yape, text="Número de operación Yape (opcional):").pack(side="left", padx=(0, 8))
        self.campo_referencia_pago = ctk.CTkEntry(
            self.panel_yape, width=200, placeholder_text="Ej: 000123456"
        )
        self.campo_referencia_pago.pack(side="left")
        # Empieza oculto (EFECTIVO es el método por defecto).

    def _alternar_campos_pago(self, metodo: str):
        if metodo == "EFECTIVO":
            self.panel_yape.grid_forget()
            self.panel_efectivo.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        else:
            self.panel_efectivo.grid_forget()
            self.panel_yape.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

    # -----------------------------------------------------------------
    # Registrar venta
    # -----------------------------------------------------------------

    def _crear_boton_registrar(self):
        self.boton_registrar = ctk.CTkButton(
            self.scroll,
            text="✅ Registrar venta",
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._registrar_venta,
        )
        self.boton_registrar.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 24))

    def _registrar_venta(self):
        if not self.carrito:
            messagebox.showwarning(
                "Carrito vacío", "Agrega al menos un producto al carrito antes de registrar la venta.",
                parent=self,
            )
            return

        metodo_pago = self.segmento_metodo_pago.get()
        payload = {
            "cliente_id": None,
            "metodo_pago": metodo_pago,
            "detalles": [
                {
                    "producto_id": linea["producto_id"],
                    "tipo_venta": linea["tipo_venta"],
                    "cantidad": linea["cantidad"],
                }
                for linea in self.carrito
            ],
        }

        if metodo_pago == "EFECTIVO":
            texto_monto = self.campo_monto_recibido.get().strip()
            if not texto_monto:
                messagebox.showerror(
                    "Dato faltante", "Ingresa el monto recibido en efectivo.", parent=self
                )
                return
            try:
                monto = Decimal(texto_monto.replace(",", "."))
            except InvalidOperation:
                messagebox.showerror(
                    "Monto inválido", "El monto recibido debe ser un número válido.", parent=self
                )
                return
            payload["monto_recibido"] = str(monto)
        else:  # YAPE (referencia opcional, ya no bloquea la venta)
            referencia = self.campo_referencia_pago.get().strip()
            if referencia:
                payload["referencia_pago"] = referencia

        try:
            venta = self.api.crear_venta(payload)
        except ApiError as exc:
            messagebox.showerror("No se pudo registrar la venta", str(exc), parent=self)
            return

        self._mostrar_confirmacion(venta)
        self._reiniciar_formulario()

    def _mostrar_confirmacion(self, venta: dict):
        lineas = [f"Venta #{venta['id']} registrada correctamente.", f"Total: S/ {venta['total']}"]
        if venta["metodo_pago"] == "EFECTIVO":
            lineas.append(f"Monto recibido: S/ {venta['monto_recibido']}")
            lineas.append(f"Vuelto: S/ {venta['vuelto']}")
        else:
            lineas.append(f"Pago con Yape (operación: {venta['referencia_pago']})")
        messagebox.showinfo("Venta registrada", "\n".join(lineas), parent=self)

    def _reiniciar_formulario(self):
        self.carrito = []
        self._refrescar_carrito()
        self.campo_monto_recibido.delete(0, "end")
        self.campo_referencia_pago.delete(0, "end")
        self.segmento_metodo_pago.set("EFECTIVO")
        self._alternar_campos_pago("EFECTIVO")
