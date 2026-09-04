"""
app.py
------
Punto de entrada de la interfaz de escritorio del Sistema POS de
Librería/Papelería. Construida con CustomTkinter (mismo framework que
SPYDER INV PRO), consumiendo el backend FastAPI a través de `api_client.py`.

Ejecutar con:
    python app.py

Requisito: el backend debe estar corriendo (uvicorn main:app) en otra
terminal antes de abrir esta aplicación, y debe existir al menos un usuario
(créalo una vez con `python crear_usuario.py` desde la carpeta del backend).

ARQUITECTURA DE VENTANA ÚNICA:
    Existe UNA sola ventana raíz de Tkinter (`RootApp`) durante toda la vida
    de la aplicación. Login y la app principal NO son ventanas separadas:
    son dos CTkFrame que se intercambian dentro de esa misma ventana raíz
    (`_mostrar_login()` / `_al_iniciar_sesion()`). Esto es deliberado --
    crear y destruir múltiples instancias de `ctk.CTk()` (varias "ventanas
    raíz" independientes) durante la vida de un mismo proceso puede
    comportarse de forma inconsistente según la plataforma; un solo root
    con frames intercambiables es el patrón robusto recomendado en Tkinter.

Flujo:
    RootApp arranca -> muestra LoginFrame
        -> login exitoso -> muestra MainAppFrame (sidebar + vistas)
            -> "Cerrar sesión" -> vuelve a LoginFrame
            -> cerrar la ventana (X) -> termina la aplicación
"""

import customtkinter as ctk

from api_client import ApiClient
from views.login import LoginFrame
from views.inicio import InicioView
from views.productos import ProductosView
from views.ventas import VentasView
from views.reportes import ReportesView

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class RootApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Papelería POS")
        self.geometry("1100x680")
        self.minsize(900, 600)

        # Un único ApiClient para toda la vida de la app: al iniciar sesión
        # guarda el token y lo reutiliza en cada request hasta el logout.
        self.api = ApiClient()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._mostrar_login()

    def _mostrar_login(self):
        for widget in self.winfo_children():
            widget.destroy()
        login_frame = LoginFrame(self, api=self.api, on_login_exitoso=self._al_iniciar_sesion)
        login_frame.grid(row=0, column=0, sticky="nsew")

    def _al_iniciar_sesion(self, usuario: dict):
        for widget in self.winfo_children():
            widget.destroy()
        main_frame = MainAppFrame(self, api=self.api, usuario=usuario, on_cerrar_sesion=self._al_cerrar_sesion)
        main_frame.grid(row=0, column=0, sticky="nsew")

    def _al_cerrar_sesion(self):
        self.api.logout()
        self._mostrar_login()


class MainAppFrame(ctk.CTkFrame):
    """
    La app principal (sidebar + vistas) una vez que hay sesión iniciada.
    Antes era la ventana raíz completa (MainApp(ctk.CTk)); ahora es un
    CTkFrame que RootApp incrusta dentro de sí misma tras el login.

    Estructura interna (patrón clásico de app de escritorio):
        ┌─────────────┬──────────────────────────────┐
        │   Menú      │      Área de contenido        │
        │  lateral    │   (una vista a la vez, se      │
        │ (sidebar)   │    intercambian con tkraise)   │
        └─────────────┴──────────────────────────────┘
    """

    def __init__(self, master, api: ApiClient, usuario: dict, on_cerrar_sesion, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api
        self.usuario = usuario
        self.on_cerrar_sesion = on_cerrar_sesion

        self.grid_columnconfigure(0, weight=0)  # sidebar: ancho fijo
        self.grid_columnconfigure(1, weight=1)  # contenido: se expande
        self.grid_rowconfigure(0, weight=1)

        self._crear_sidebar()
        self._crear_area_contenido()

        self.mostrar_vista("inicio")

    # -----------------------------------------------------------------
    # Sidebar (menú de navegación + usuario conectado)
    # -----------------------------------------------------------------

    def _crear_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(1, weight=1)  # empuja el pie hacia abajo

        ctk.CTkLabel(
            self.sidebar,
            text="📚 Papelería",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(24, 30), sticky="w")

        # --- Menú de navegación ---
        menu = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        menu.grid(row=1, column=0, sticky="new")

        # (etiqueta interna, texto del botón, ícono)
        opciones = [
            ("inicio", "Inicio", "🏠"),
            ("productos", "Productos", "📦"),
            ("ventas", "Ventas (POS)", "💰"),
            ("reportes", "Reportes", "📊"),
        ]

        self.botones_menu = {}
        for clave, texto, icono in opciones:
            boton = ctk.CTkButton(
                menu,
                text=f"{icono}  {texto}",
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                command=lambda c=clave: self.mostrar_vista(c),
            )
            boton.pack(fill="x", padx=12, pady=4)
            self.botones_menu[clave] = boton

        # --- Pie del sidebar: usuario conectado + cerrar sesión ---
        pie = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        pie.grid(row=2, column=0, sticky="sew", padx=12, pady=16)

        rol_legible = "Administrador" if self.usuario.get("rol") == "ADMIN" else "Cajero"
        ctk.CTkLabel(
            pie,
            text=f"👤 {self.usuario.get('nombre_completo', '')}",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=170,
        ).pack(fill="x", pady=(0, 0))
        ctk.CTkLabel(
            pie, text=rol_legible, anchor="w", font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            pie, text="Cerrar sesión", fg_color="gray", height=28, command=self._cerrar_sesion
        ).pack(fill="x")

    def _cerrar_sesion(self):
        self.on_cerrar_sesion()

    def _resaltar_boton_activo(self, clave_activa: str):
        """Cambia el color del botón de la vista activa para indicar dónde estás."""
        for clave, boton in self.botones_menu.items():
            if clave == clave_activa:
                boton.configure(fg_color=("gray75", "gray30"))
            else:
                boton.configure(fg_color="transparent")

    # -----------------------------------------------------------------
    # Área de contenido (vistas apiladas)
    # -----------------------------------------------------------------

    def _crear_area_contenido(self):
        self.contenedor = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray95", "gray10"))
        self.contenedor.grid(row=0, column=1, sticky="nsew")
        self.contenedor.grid_rowconfigure(0, weight=1)
        self.contenedor.grid_columnconfigure(0, weight=1)

        # Cada vista se crea una sola vez y se apila en la misma celda con
        # tkraise() para cambiar entre ellas sin recrearlas.
        self.vistas = {
            "inicio": InicioView(self.contenedor, api=self.api),
            "productos": ProductosView(self.contenedor, api=self.api, usuario=self.usuario),
            "ventas": VentasView(self.contenedor, api=self.api),
            "reportes": ReportesView(self.contenedor, api=self.api),
        }

        for vista in self.vistas.values():
            vista.grid(row=0, column=0, sticky="nsew")

    def mostrar_vista(self, clave: str):
        """Trae al frente la vista correspondiente y resalta su botón en el menú."""
        self.vistas[clave].tkraise()
        self._resaltar_boton_activo(clave)


if __name__ == "__main__":
    app = RootApp()
    app.mainloop()
