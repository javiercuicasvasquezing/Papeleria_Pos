"""
views/importar_excel_dialog.py
--------------------------------
Importación inteligente: elegir modo (agregar nuevos / actualizar+crear /
reemplazar todo) -> elegir archivo -> vista previa -> confirmar.
Coincidencia de productos existentes por (nombre, marca) -- el Excel de
este negocio no trae código de barras.
"""

from tkinter import filedialog, messagebox, simpledialog, ttk

import customtkinter as ctk

from api_client import ApiClient, ApiError


class ImportarExcelDialog(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, usuario: dict, on_importado):
        super().__init__(master)
        self.api = api
        self.usuario = usuario
        self.on_importado = on_importado
        self.filas_validas: list[dict] = []

        self.title("Importar inventario desde Excel")
        self.geometry("680x560")
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self, text="Importar desde Excel", font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # --- Modo de importación ---
        marco_modo = ctk.CTkFrame(self, fg_color="transparent")
        marco_modo.grid(row=1, column=0, padx=20, sticky="ew")
        self.modo = ctk.StringVar(value="agregar_nuevos")
        ctk.CTkRadioButton(
            marco_modo, text="Agregar únicamente productos nuevos", variable=self.modo,
            value="agregar_nuevos",
        ).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(
            marco_modo, text="Actualizar existentes y crear nuevos (recomendado)",
            variable=self.modo, value="actualizar_y_crear",
        ).pack(anchor="w", pady=2)

        self.check_stock_var = ctk.BooleanVar(value=False)
        self.check_stock = ctk.CTkCheckBox(
            marco_modo, text="También actualizar el stock (si no, se conserva el actual)",
            variable=self.check_stock_var,
        )
        self.check_stock.pack(anchor="w", padx=(24, 0), pady=(0, 6))

        if self.usuario.get("rol") == "ADMIN":
            ctk.CTkRadioButton(
                marco_modo, text="⚠️ Reemplazar todo el inventario (elimina y vuelve a crear)",
                variable=self.modo, value="reemplazar_todo",
            ).pack(anchor="w", pady=2)

        self.label_resumen = ctk.CTkLabel(self, text="Selecciona un archivo .xlsx para comenzar.")
        self.label_resumen.grid(row=2, column=0, padx=20, pady=(10, 4), sticky="w")

        estilo = ttk.Style()
        estilo.theme_use("clam")
        cols = ("fila", "nombre", "marca", "precio_unidad", "stock", "estado")
        self.tabla = ttk.Treeview(self, columns=cols, show="headings", height=12)
        encabezados = {
            "fila": "Fila", "nombre": "Nombre", "marca": "Marca",
            "precio_unidad": "P. unidad", "stock": "Stock", "estado": "Estado",
        }
        anchos = {"fila": 50, "nombre": 200, "marca": 100, "precio_unidad": 80, "stock": 60, "estado": 140}
        for c in cols:
            self.tabla.heading(c, text=encabezados[c])
            self.tabla.column(c, width=anchos[c], anchor="w" if c in ("nombre", "estado") else "center")
        self.tabla.tag_configure("error", foreground="#c0392b")
        self.tabla.tag_configure("actualizar", foreground="#b8860b")
        self.tabla.grid(row=3, column=0, sticky="nsew", padx=20, pady=(6, 10))

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))
        botones.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(botones, text="Elegir archivo...", command=self._elegir_archivo).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ctk.CTkButton(botones, text="Cancelar", fg_color="gray", command=self.destroy).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        self.boton_importar = ctk.CTkButton(
            botones, text="Importar", state="disabled", command=self._confirmar
        )
        self.boton_importar.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona el Excel de inventario",
            filetypes=[("Archivos Excel", "*.xlsx")], parent=self,
        )
        if not ruta:
            return
        self.ruta_archivo = ruta
        self.label_resumen.configure(text="Analizando archivo...")
        self.update_idletasks()

        try:
            resultado = self.api.importar_excel_vista_previa(ruta)
        except ApiError as exc:
            messagebox.showerror("Error al leer el archivo", str(exc), parent=self)
            return

        if resultado.get("error_general"):
            messagebox.showerror("Archivo inválido", resultado["error_general"], parent=self)
            return

        self.tabla.delete(*self.tabla.get_children())
        self.filas_validas = []

        for fila in resultado["filas"]:
            if fila["error"]:
                self.tabla.insert("", "end", values=(
                    fila["fila_excel"], fila.get("nombre") or "—", fila.get("marca") or "—",
                    "—", "—", fila["error"]), tags=("error",))
            else:
                estado = "Nuevo" if fila["accion"] == "crear" else "Ya existe (se actualizará)"
                if fila.get("advertencia"):
                    estado += " ⚠ revisar precio"
                tag = ("actualizar",) if fila["accion"] != "crear" or fila.get("advertencia") else ()
                self.tabla.insert("", "end", values=(
                    fila["fila_excel"], fila["nombre"], fila.get("marca") or "—",
                    f"S/ {fila['precio_venta_unidad']}", fila["stock_unidades"], estado), tags=tag)
                self.filas_validas.append(fila)

        self.label_resumen.configure(
            text=(f"Encontrados: {resultado['total']}  |  Nuevos: {resultado['nuevos']}  |  "
                  f"Ya existen: {resultado['existentes']}  |  Con errores: {resultado['con_errores']}")
        )
        self.boton_importar.configure(state="normal" if self.filas_validas else "disabled")

    def _confirmar(self):
        if not self.filas_validas:
            return
        modo = self.modo.get()

        if modo == "reemplazar_todo":
            respuesta = simpledialog.askstring(
                "Confirmación requerida",
                "Esta operación ELIMINARÁ productos sin ventas registradas y volverá a crear "
                "el inventario desde el Excel. Esta acción no puede deshacerse.\n\n"
                "Escribe CONFIRMAR para continuar:",
                parent=self,
            )
            if respuesta != "CONFIRMAR":
                messagebox.showinfo("Cancelado", "No se escribió CONFIRMAR. No se hizo ningún cambio.", parent=self)
                return
            try:
                resultado = self.api.importar_excel_reemplazar_todo(self.filas_validas, respuesta)
            except ApiError as exc:
                messagebox.showerror("No se pudo importar", str(exc), parent=self)
                return
            messagebox.showinfo(
                "Importación completa",
                f"Eliminados: {resultado['eliminados']}\n"
                f"Conservados (tienen ventas): {resultado['conservados_por_tener_ventas']}\n"
                f"Nuevos productos creados: {resultado['nuevos']}",
                parent=self,
            )
        else:
            try:
                resultado = self.api.importar_excel_confirmar(
                    modo, self.check_stock_var.get(), self.filas_validas
                )
            except ApiError as exc:
                messagebox.showerror("No se pudo importar", str(exc), parent=self)
                return
            messagebox.showinfo(
                "Importación completa",
                f"Nuevos: {resultado['nuevos']}\nActualizados: {resultado['actualizados']}\n"
                f"Omitidos: {resultado['omitidos']}",
                parent=self,
            )

        self.on_importado()
        self.destroy()
