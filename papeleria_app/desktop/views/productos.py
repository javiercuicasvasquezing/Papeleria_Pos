"""
views/productos.py
-------------------
Pantalla de Inventario/Productos (Módulo 3): catálogo, precios y stock.

Búsqueda unificada (nombre O código de barras) en un solo campo, con
resultados en vivo mientras se escribe (sin botón), usando LIKE en SQL
del lado del backend -- nunca carga todo el catálogo en memoria.
"""

from tkinter import messagebox, ttk, filedialog

import customtkinter as ctk

from api_client import ApiClient, ApiError
from views.producto_dialog import ProductoDialog
from views.importar_excel_dialog import ImportarExcelDialog

# Umbral bajo el cual el stock se marca como "bajo" en la columna de estado.
# Ajusta este número si tu papelería maneja volúmenes distintos.
UMBRAL_STOCK_BAJO = 10

# Milisegundos de espera tras la última tecla antes de disparar la búsqueda
# (evita golpear la API en cada pulsación; es lo suficientemente corto para
# sentirse instantáneo).
RETRASO_BUSQUEDA_MS = 300


class ProductosView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, usuario: dict, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api
        self.usuario = usuario
        self.productos_por_id = {}  # cache: id -> dict del producto (para abrir el diálogo de edición)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._crear_encabezado()
        self._crear_barra_busqueda()
        self._crear_tabla()

        self.after(100, self.cargar_productos)

    # -----------------------------------------------------------------
    # Encabezado: título + botones de acción
    # -----------------------------------------------------------------

    def _crear_encabezado(self):
        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        encabezado.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            encabezado, text="📦 Productos", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        botones = ctk.CTkFrame(encabezado, fg_color="transparent")
        botones.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            botones, text="🔄 Actualizar", width=110, fg_color="gray", command=self.cargar_productos
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            botones, text="✏️ Editar", width=110, command=self._abrir_edicion
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            botones, text="🗑️ Eliminar", width=110, fg_color="#a03030", command=self._eliminar_seleccionados
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            botones, text="📥 Importar Excel", width=140, fg_color="gray", command=self._abrir_importacion
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            botones, text="📤 Exportar Excel", width=140, fg_color="gray", command=self._exportar_excel
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            botones, text="➕ Nuevo producto", width=150, command=self._abrir_creacion
        ).pack(side="left", padx=4)

    # -----------------------------------------------------------------
    # Barra de búsqueda
    # -----------------------------------------------------------------

    def _crear_barra_busqueda(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        barra.grid_columnconfigure(0, weight=1)

        self._job_busqueda_pendiente = None

        self.campo_busqueda = ctk.CTkEntry(
            barra, placeholder_text="Buscar por nombre o código de barras..."
        )
        self.campo_busqueda.grid(row=0, column=0, sticky="ew")
        # Búsqueda en vivo: cada tecla reprograma la búsqueda RETRASO_BUSQUEDA_MS
        # más adelante, cancelando la anterior si el usuario sigue escribiendo
        # (o si un lector de código de barras USB "escribe" muy rápido).
        self.campo_busqueda.bind("<KeyRelease>", self._al_escribir_busqueda)

        ctk.CTkButton(
            barra, text="Ver todos", width=90, fg_color="gray", command=self.cargar_productos
        ).grid(row=0, column=1, padx=(8, 0))

    # -----------------------------------------------------------------
    # Tabla (ttk.Treeview)
    # -----------------------------------------------------------------

    def _crear_tabla(self):
        contenedor = ctk.CTkFrame(self)
        contenedor.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 20))
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(0, weight=1)

        columnas = (
            "codigo_barras",
            "nombre",
            "marca",
            "precio_compra",
            "precio_unidad",
            "precio_caja",
            "uds_caja",
            "stock",
            "estado",
        )
        encabezados = {
            "codigo_barras": "Código de barras",
            "nombre": "Nombre",
            "marca": "Marca",
            "precio_compra": "Precio compra",
            "precio_unidad": "Precio x unidad",
            "precio_caja": "Precio x caja",
            "uds_caja": "Uds/caja",
            "stock": "Stock (uds)",
            "estado": "Estado",
        }
        anchos = {
            "codigo_barras": 130,
            "nombre": 220,
            "marca": 110,
            "precio_compra": 100,
            "precio_unidad": 110,
            "precio_caja": 110,
            "uds_caja": 80,
            "stock": 90,
            "estado": 100,
        }

        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Treeview", rowheight=28, font=("Segoe UI", 11))
        estilo.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))

        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="extended")
        for col in columnas:
            self.tabla.heading(col, text=encabezados[col])
            anchor = "center" if col in ("uds_caja", "stock", "estado", "precio_compra") else "w"
            self.tabla.column(col, width=anchos[col], anchor=anchor)

        self.tabla.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        self.tabla.bind("<Double-1>", lambda _evt: self._abrir_edicion())

        # Colores por estado de stock (se aplican como "tag" a cada fila).
        self.tabla.tag_configure("sin_stock", foreground="#c0392b")
        self.tabla.tag_configure("stock_bajo", foreground="#b8860b")
        self.tabla.tag_configure("stock_normal", foreground="")

        scrollbar = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=1)

        self.label_estado = ctk.CTkLabel(self, text="", text_color=("gray30", "gray70"))
        self.label_estado.grid(row=3, column=0, sticky="w", padx=28, pady=(0, 10))

    # -----------------------------------------------------------------
    # Carga y búsqueda de datos
    # -----------------------------------------------------------------

    def cargar_productos(self):
        self.campo_busqueda.delete(0, "end")
        try:
            resultado = self.api.listar_productos(limit=200)
        except ApiError as exc:
            messagebox.showerror("Error al cargar productos", str(exc), parent=self)
            return
        self._mostrar_productos(resultado["items"])

    def _al_escribir_busqueda(self, _evento=None):
        """
        Se dispara con cada tecla. Reprograma la búsqueda real
        RETRASO_BUSQUEDA_MS después, cancelando cualquier búsqueda que
        todavía estuviera pendiente -- así, si el usuario (o un lector de
        código de barras USB) escribe varios caracteres seguidos muy
        rápido, solo se dispara UNA consulta al final, no una por tecla.
        """
        if self._job_busqueda_pendiente is not None:
            self.after_cancel(self._job_busqueda_pendiente)
        self._job_busqueda_pendiente = self.after(RETRASO_BUSQUEDA_MS, self.buscar)

    def buscar(self):
        self._job_busqueda_pendiente = None
        texto = self.campo_busqueda.get().strip()
        if not texto:
            self.cargar_productos()
            return
        try:
            # Búsqueda unificada: nombre O código de barras, insensible a
            # mayúsculas/minúsculas, coincidencia parcial (LIKE del lado del
            # backend -- nunca se trae todo el catálogo a memoria).
            if texto.isdigit() and len(texto) >= 6:
                resultado = self.api.buscar_productos(codigo_barras=texto)
                if not resultado["items"]:
                    resultado = self.api.buscar_productos(q=texto)
            else:
                resultado = self.api.buscar_productos(q=texto)
        except ApiError as exc:
            messagebox.showerror("Error al buscar", str(exc), parent=self)
            return
        self._mostrar_productos(resultado["items"])

    @staticmethod
    def _estado_stock(stock: int) -> tuple[str, str]:
        """Devuelve (texto, tag) según el nivel de stock."""
        if stock <= 0:
            return "Sin stock", "sin_stock"
        if stock < UMBRAL_STOCK_BAJO:
            return "Stock bajo", "stock_bajo"
        return "Normal", "stock_normal"

    def _mostrar_productos(self, productos: list[dict]):
        self.tabla.delete(*self.tabla.get_children())
        self.productos_por_id = {p["id"]: p for p in productos}

        for p in productos:
            precio_caja = f"S/ {p['precio_venta_caja']}" if p.get("precio_venta_caja") is not None else "—"
            uds_caja = p["unidades_por_caja"] if p.get("precio_venta_caja") is not None else "—"
            texto_estado, tag_estado = self._estado_stock(p["stock_unidades"])
            self.tabla.insert(
                "",
                "end",
                iid=str(p["id"]),
                values=(
                    p.get("codigo_barras") or "—",
                    p["nombre"],
                    p.get("marca") or "—",
                    f"S/ {p['precio_compra']}",
                    f"S/ {p['precio_venta_unidad']}",
                    precio_caja,
                    uds_caja,
                    p["stock_unidades"],
                    texto_estado,
                ),
                tags=(tag_estado,),
            )

        self.label_estado.configure(text=f"{len(productos)} producto(s) encontrado(s).")

    # -----------------------------------------------------------------
    # Acciones: crear / editar
    # -----------------------------------------------------------------

    def _abrir_creacion(self):
        ProductoDialog(self, api=self.api, on_guardado=self.cargar_productos, producto=None)

    def _abrir_importacion(self):
        ImportarExcelDialog(self, api=self.api, usuario=self.usuario, on_importado=self.cargar_productos)

    def _eliminar_seleccionados(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Nada seleccionado", "Selecciona uno o más productos para eliminar.", parent=self)
            return
        ids = [int(s) for s in seleccion]
        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar {len(ids)} producto(s) seleccionado(s)? Esta acción no puede deshacerse.",
            parent=self,
        ):
            return
        try:
            resultado = self.api.eliminar_productos(ids)
        except ApiError as exc:
            messagebox.showerror("Error al eliminar", str(exc), parent=self)
            return

        mensaje = f"Eliminados: {resultado['eliminados']}"
        if resultado["no_eliminables"]:
            detalle = "\n".join(f"- {p['nombre']}: {p['motivo']}" for p in resultado["no_eliminables"])
            mensaje += f"\n\nNo se pudieron eliminar {len(resultado['no_eliminables'])}:\n{detalle}"
        messagebox.showinfo("Resultado", mensaje, parent=self)
        self.cargar_productos()

    def _exportar_excel(self):
        ruta = filedialog.asksaveasfilename(
            title="Guardar inventario como...",
            defaultextension=".xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            initialfile="inventario_exportado.xlsx",
            parent=self,
        )
        if not ruta:
            return
        try:
            self.api.exportar_excel(ruta)
        except ApiError as exc:
            messagebox.showerror("Error al exportar", str(exc), parent=self)
            return
        messagebox.showinfo("Exportado", f"Inventario guardado en:\n{ruta}", parent=self)

    def _abrir_edicion(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning(
                "Ningún producto seleccionado",
                "Selecciona un producto de la tabla (haz clic sobre una fila) para editarlo.",
                parent=self,
            )
            return
        producto_id = int(seleccion[0])
        producto = self.productos_por_id.get(producto_id)
        if producto is None:
            return
        ProductoDialog(self, api=self.api, on_guardado=self.cargar_productos, producto=producto)
