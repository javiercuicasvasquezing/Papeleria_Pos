"""
views/inicio.py
----------------
Vista de Inicio / Dashboard. Es la primera pantalla que ve el usuario al
abrir la aplicación. Por ahora (Módulo 5) muestra el estado de conexión con
el backend y un botón para volver a verificarla; en módulos futuros se le
pueden sumar accesos rápidos o resúmenes (ej. "ventas de hoy").
"""

import customtkinter as ctk

from api_client import ApiClient


class InicioView(ctk.CTkFrame):
    """Pantalla de bienvenida + estado de conexión con la API local."""

    def __init__(self, master, api: ApiClient, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api

        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text="Sistema POS - Librería/Papelería",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        titulo.grid(row=0, column=0, pady=(40, 10), sticky="n")

        subtitulo = ctk.CTkLabel(
            self,
            text="Bienvenido. Usa el menú de la izquierda para navegar.",
            font=ctk.CTkFont(size=14),
            text_color=("gray30", "gray70"),
        )
        subtitulo.grid(row=1, column=0, pady=(0, 30), sticky="n")

        # --- Tarjeta de estado de conexión ---
        tarjeta = ctk.CTkFrame(self, corner_radius=12)
        tarjeta.grid(row=2, column=0, padx=40, pady=10, sticky="n")

        ctk.CTkLabel(
            tarjeta, text="Estado del servidor local", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(16, 4), sticky="w")

        self.indicador = ctk.CTkLabel(
            tarjeta, text="●", font=ctk.CTkFont(size=18), text_color="gray"
        )
        self.indicador.grid(row=1, column=0, padx=(20, 6), pady=(0, 16))

        self.estado_label = ctk.CTkLabel(tarjeta, text="Verificando...", font=ctk.CTkFont(size=13))
        self.estado_label.grid(row=1, column=1, padx=(0, 12), pady=(0, 16), sticky="w")

        self.boton_reintentar = ctk.CTkButton(
            tarjeta, text="Volver a verificar", width=160, command=self.verificar_conexion
        )
        self.boton_reintentar.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 16))

        # Verificación inicial automática al abrir la vista.
        self.after(200, self.verificar_conexion)

    def verificar_conexion(self):
        self.estado_label.configure(text="Verificando...")
        self.indicador.configure(text_color="gray")
        self.update_idletasks()

        conectado = self.api.verificar_conexion()

        if conectado:
            self.indicador.configure(text_color="#2fa84f")  # verde
            self.estado_label.configure(text=f"Conectado a {self.api.base_url}")
        else:
            self.indicador.configure(text_color="#d64545")  # rojo
            self.estado_label.configure(
                text="Sin conexión. ¿Está corriendo 'uvicorn main:app'?"
            )
