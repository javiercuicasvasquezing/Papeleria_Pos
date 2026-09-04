"""
views/placeholder.py
---------------------
Vista genérica temporal para las secciones que todavía no se han
implementado (Productos, Clientes, Ventas se reemplazarán en los
Módulos 6, 7 y 8 respectivamente). Evita tener pantallas en blanco o que
la app truene al hacer clic en una sección aún no construida.
"""

import customtkinter as ctk


class PlaceholderView(ctk.CTkFrame):
    """Pantalla temporal que indica en qué módulo se implementará esta sección."""

    def __init__(self, master, titulo: str, modulo: str, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.grid(row=0, column=0)

        ctk.CTkLabel(
            contenedor, text=titulo, font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            contenedor,
            text=f"Esta sección se implementará en el {modulo}.",
            font=ctk.CTkFont(size=14),
            text_color=("gray30", "gray70"),
        ).pack()
