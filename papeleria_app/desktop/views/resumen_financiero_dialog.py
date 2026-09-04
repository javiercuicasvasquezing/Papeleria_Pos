"""
views/resumen_financiero_dialog.py
------------------------------------
Ventana rápida: elegir un rango de fechas y ver cuánto se vendió por
Efectivo y por Yape (sin generar ningún Excel), reutilizando el endpoint
GET /reportes/resumen.
"""

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from api_client import ApiClient, ApiError


class ResumenFinancieroDialog(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient):
        super().__init__(master)
        self.api = api

        self.title("Resumen financiero")
        self.geometry("380x360")
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Resumen financiero", font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        hoy = date.today().strftime("%d/%m/%Y")
        ctk.CTkLabel(self, text="Desde:").grid(row=1, column=0, padx=20, sticky="w")
        self.campo_desde = ctk.CTkEntry(self, placeholder_text=hoy)
        self.campo_desde.grid(row=2, column=0, padx=20, sticky="ew")
        self.campo_desde.insert(0, hoy)

        ctk.CTkLabel(self, text="Hasta:").grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.campo_hasta = ctk.CTkEntry(self, placeholder_text=hoy)
        self.campo_hasta.grid(row=4, column=0, padx=20, sticky="ew")
        self.campo_hasta.insert(0, hoy)

        ctk.CTkButton(self, text="Consultar", command=self._consultar).grid(
            row=5, column=0, padx=20, pady=16, sticky="ew"
        )

        self.marco_resultado = ctk.CTkFrame(self, corner_radius=12)
        self.marco_resultado.grid(row=6, column=0, padx=20, sticky="ew")
        self.label_resultado = ctk.CTkLabel(
            self.marco_resultado, text="Elige un rango y presiona Consultar.", justify="left"
        )
        self.label_resultado.pack(padx=16, pady=16, anchor="w")

    @staticmethod
    def _convertir_fecha(texto: str) -> str:
        dia, mes, anio = texto.strip().split("/")
        return f"{int(anio):04d}-{int(mes):02d}-{int(dia):02d}"

    def _consultar(self):
        try:
            desde = self._convertir_fecha(self.campo_desde.get())
            hasta = self._convertir_fecha(self.campo_hasta.get())
        except ValueError:
            messagebox.showerror("Fecha inválida", "Usa el formato dd/mm/aaaa.", parent=self)
            return
        try:
            resumen = self.api.resumen_financiero(desde, hasta)
        except ApiError as exc:
            self.label_resultado.configure(text=str(exc))
            return

        texto = (
            f"Ventas realizadas: {resumen['cantidad_ventas']}\n"
            f"Unidades vendidas: {resumen['unidades_vendidas']}\n\n"
            f"💵 Efectivo:  S/ {resumen['total_efectivo']:.2f}\n"
            f"📱 Yape:        S/ {resumen['total_yape']:.2f}\n"
            f"───────────────────────\n"
            f"Total:          S/ {resumen['total_vendido']:.2f}"
        )
        self.label_resultado.configure(text=texto, font=ctk.CTkFont(size=13))
