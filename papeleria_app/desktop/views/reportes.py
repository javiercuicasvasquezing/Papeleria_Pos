"""
views/reportes.py
------------------
Pantalla de Reportes: generar Excel de ventas de un día o de un rango de
fechas. El archivo se guarda automáticamente en reportes/ (en el servidor)
y además se ofrece guardar una copia donde el usuario elija.
"""

from tkinter import filedialog, messagebox

import customtkinter as ctk

from api_client import ApiClient, ApiError


class ReportesView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="📊 Reportes", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 16))

        # --- Reporte diario ---
        marco1 = ctk.CTkFrame(self, corner_radius=12)
        marco1.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 16))
        ctk.CTkLabel(
            marco1, text="Reporte diario", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))

        ctk.CTkLabel(marco1, text="Fecha (dd/mm/aaaa):").grid(row=1, column=0, padx=(16, 8), pady=(0, 16))
        self.campo_fecha_diario = ctk.CTkEntry(marco1, placeholder_text="11/08/2026", width=140)
        self.campo_fecha_diario.grid(row=1, column=1, sticky="w", pady=(0, 16))
        ctk.CTkButton(
            marco1, text="Generar reporte diario", command=self._generar_diario
        ).grid(row=1, column=2, padx=16, pady=(0, 16))

        # --- Reporte por rango ---
        marco2 = ctk.CTkFrame(self, corner_radius=12)
        marco2.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        ctk.CTkLabel(
            marco2, text="Reporte por rango de fechas", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 8))

        ctk.CTkLabel(marco2, text="Desde:").grid(row=1, column=0, padx=(16, 8), pady=(0, 16))
        self.campo_desde = ctk.CTkEntry(marco2, placeholder_text="01/08/2026", width=120)
        self.campo_desde.grid(row=1, column=1, pady=(0, 16))
        ctk.CTkLabel(marco2, text="Hasta:").grid(row=1, column=2, padx=(16, 8), pady=(0, 16))
        self.campo_hasta = ctk.CTkEntry(marco2, placeholder_text="11/08/2026", width=120)
        self.campo_hasta.grid(row=1, column=3, pady=(0, 16))
        ctk.CTkButton(
            marco2, text="Generar reporte por rango", command=self._generar_rango
        ).grid(row=1, column=4, padx=16, pady=(0, 16))

        self.label_estado = ctk.CTkLabel(self, text="", text_color=("gray30", "gray70"))
        self.label_estado.grid(row=3, column=0, sticky="w", padx=28)

    @staticmethod
    def _convertir_fecha(texto: str) -> str:
        """dd/mm/aaaa -> aaaa-mm-dd (lo que espera la API). Lanza ValueError si el formato no es válido."""
        partes = texto.strip().split("/")
        if len(partes) != 3:
            raise ValueError("Usa el formato dd/mm/aaaa.")
        dia, mes, anio = partes
        return f"{int(anio):04d}-{int(mes):02d}-{int(dia):02d}"

    def _guardar_y_avisar(self, contenido: bytes, nombre_sugerido: str):
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte como...",
            defaultextension=".xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            initialfile=nombre_sugerido,
            parent=self,
        )
        if not ruta:
            self.label_estado.configure(
                text="El reporte ya quedó guardado en la carpeta 'reportes/' del sistema."
            )
            return
        with open(ruta, "wb") as f:
            f.write(contenido)
        messagebox.showinfo(
            "Reporte generado",
            f"Reporte guardado en:\n{ruta}\n\n(también se guardó una copia automática en la carpeta 'reportes/')",
            parent=self,
        )

    def _generar_diario(self):
        try:
            fecha_api = self._convertir_fecha(self.campo_fecha_diario.get())
        except ValueError as exc:
            messagebox.showerror("Fecha inválida", str(exc), parent=self)
            return
        try:
            contenido = self.api.generar_reporte_diario(fecha_api)
        except ApiError as exc:
            messagebox.showerror("No se pudo generar el reporte", str(exc), parent=self)
            return
        self._guardar_y_avisar(contenido, f"Reporte_Ventas_{fecha_api}.xlsx")

    def _generar_rango(self):
        try:
            desde_api = self._convertir_fecha(self.campo_desde.get())
            hasta_api = self._convertir_fecha(self.campo_hasta.get())
        except ValueError as exc:
            messagebox.showerror("Fecha inválida", str(exc), parent=self)
            return
        try:
            contenido = self.api.generar_reporte_rango(desde_api, hasta_api)
        except ApiError as exc:
            messagebox.showerror("No se pudo generar el reporte", str(exc), parent=self)
            return
        self._guardar_y_avisar(contenido, f"Reporte_Ventas_{desde_api}_a_{hasta_api}.xlsx")
