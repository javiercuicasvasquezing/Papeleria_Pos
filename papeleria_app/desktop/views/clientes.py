"""
views/clientes.py
------------------
Pantalla de Clientes (Módulo 7).

Flujo pensado tal cual se usaría en el mostrador:
    1. El vendedor escribe (o escanea) el DNI/RUC del cliente y presiona
       "Buscar" (o Enter).
    2. Si el cliente existe, se muestra su información en una tarjeta.
    3. Si no existe, se ofrece registrarlo ahí mismo con "Nuevo cliente".

No hay listado general de clientes porque el backend (Módulo 3) no expone
ese endpoint a propósito -- el registro de clientes es opcional/básico, y la
consulta siempre parte de un número de documento conocido.
"""

from tkinter import messagebox

import customtkinter as ctk

from api_client import ApiClient, ApiError
from views.cliente_dialog import ClienteDialog


class ClientesView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.api = api

        self.grid_columnconfigure(0, weight=1)

        self._crear_encabezado()
        self._crear_buscador()
        self._crear_tarjeta_resultado()

    # -----------------------------------------------------------------
    # Encabezado
    # -----------------------------------------------------------------

    def _crear_encabezado(self):
        ctk.CTkLabel(
            self, text="👥 Clientes", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="Busca un cliente por su DNI o RUC, o registra uno nuevo.",
            text_color=("gray30", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

    # -----------------------------------------------------------------
    # Buscador
    # -----------------------------------------------------------------

    def _crear_buscador(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 20))
        barra.grid_columnconfigure(0, weight=1)

        self.campo_documento = ctk.CTkEntry(
            barra, placeholder_text="Número de DNI o RUC..."
        )
        self.campo_documento.grid(row=0, column=0, sticky="ew")
        self.campo_documento.bind("<Return>", lambda _evt: self.buscar())

        ctk.CTkButton(barra, text="Buscar", width=90, command=self.buscar).grid(
            row=0, column=1, padx=(8, 0)
        )
        ctk.CTkButton(
            barra, text="➕ Nuevo cliente", width=150, command=self._abrir_creacion
        ).grid(row=0, column=2, padx=(8, 0))

    # -----------------------------------------------------------------
    # Tarjeta de resultado
    # -----------------------------------------------------------------

    def _crear_tarjeta_resultado(self):
        self.tarjeta = ctk.CTkFrame(self, corner_radius=12)
        self.tarjeta.grid(row=3, column=0, sticky="ew", padx=24)
        self.tarjeta.grid_columnconfigure(0, weight=1)

        self.label_titulo_resultado = ctk.CTkLabel(
            self.tarjeta,
            text="Busca un cliente para ver su información aquí.",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.label_titulo_resultado.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))

        self.label_detalle = ctk.CTkLabel(
            self.tarjeta, text="", justify="left", anchor="w", text_color=("gray30", "gray70")
        )
        self.label_detalle.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))

    # -----------------------------------------------------------------
    # Acciones
    # -----------------------------------------------------------------

    def buscar(self):
        documento = self.campo_documento.get().strip()
        if not documento:
            messagebox.showwarning(
                "Documento vacío", "Escribe un número de DNI o RUC para buscar.", parent=self
            )
            return

        try:
            cliente = self.api.obtener_cliente_por_documento(documento)
        except ApiError as exc:
            messagebox.showerror("Error al buscar", str(exc), parent=self)
            return

        if cliente is None:
            self.label_titulo_resultado.configure(
                text=f"No se encontró ningún cliente con el documento '{documento}'."
            )
            self.label_detalle.configure(
                text="Puedes registrarlo con el botón 'Nuevo cliente'."
            )
            return

        self._mostrar_cliente(cliente)

    def _mostrar_cliente(self, cliente: dict):
        self.label_titulo_resultado.configure(text=cliente.get("nombre_o_razon_social") or "(Sin nombre registrado)")
        tipo = cliente.get("tipo_documento") or "—"
        numero = cliente.get("numero_documento") or "—"
        direccion = cliente.get("direccion") or "—"
        detalle = (
            f"Documento: {tipo} {numero}\n"
            f"Dirección: {direccion}\n"
            f"Cliente desde: {cliente.get('fecha_registro', '—')[:10]}"
        )
        self.label_detalle.configure(text=detalle)

    def _abrir_creacion(self):
        ClienteDialog(self, api=self.api, on_guardado=self._al_crear_cliente)

    def _al_crear_cliente(self, cliente_creado: dict):
        # Tras crear, mostramos de una vez sus datos y pre-llenamos el buscador
        # con su documento (si tiene), para que el flujo se sienta continuo.
        self.campo_documento.delete(0, "end")
        if cliente_creado.get("numero_documento"):
            self.campo_documento.insert(0, cliente_creado["numero_documento"])
        self._mostrar_cliente(cliente_creado)
