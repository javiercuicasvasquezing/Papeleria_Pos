"""
views/cliente_dialog.py
------------------------
Ventana modal (CTkToplevel) para registrar un nuevo cliente.

A diferencia de Producto, aquí NO existe un modo "editar": el backend
(Módulo 3 de la API) solo expone `POST /clientes/` y `GET /clientes/{documento}`,
sin un endpoint de actualización. Esto es intencional -- el registro de
clientes es "opcional o básico" según los requisitos del negocio -- así que
este diálogo solo cubre creación.
"""

from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from api_client import ApiClient, ApiError


class ClienteDialog(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, on_guardado: Callable[[dict], None]):
        super().__init__(master)
        self.api = api
        self.on_guardado = on_guardado

        self.title("Nuevo cliente")
        self.geometry("400x420")
        self.resizable(False, False)

        self.transient(master)
        self.grab_set()

        self._construir_formulario()
        self.after(50, lambda: self.campo_nombre.focus())

    def _construir_formulario(self):
        self.grid_columnconfigure(0, weight=1)

        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.grid(row=0, column=0, padx=24, pady=20, sticky="nsew")
        contenedor.grid_columnconfigure(0, weight=1)

        nota = (
            "El documento es opcional (para ventas rápidas de mostrador). "
            "Si indicas uno, debes elegir el tipo."
        )
        ctk.CTkLabel(
            contenedor,
            text=nota,
            anchor="w",
            justify="left",
            wraplength=340,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(contenedor, text="Nombre o razón social *", anchor="w").grid(
            row=1, column=0, sticky="w", pady=(0, 2)
        )
        self.campo_nombre = ctk.CTkEntry(contenedor)
        self.campo_nombre.grid(row=2, column=0, sticky="ew")

        ctk.CTkLabel(contenedor, text="Tipo de documento", anchor="w").grid(
            row=3, column=0, sticky="w", pady=(14, 2)
        )
        self.combo_tipo_documento = ctk.CTkComboBox(
            contenedor, values=["(Ninguno)", "DNI", "RUC", "CE"], state="readonly"
        )
        self.combo_tipo_documento.set("(Ninguno)")
        self.combo_tipo_documento.grid(row=4, column=0, sticky="ew")

        ctk.CTkLabel(contenedor, text="Número de documento", anchor="w").grid(
            row=5, column=0, sticky="w", pady=(14, 2)
        )
        self.campo_numero_documento = ctk.CTkEntry(
            contenedor, placeholder_text="DNI: 8 dígitos · RUC: 11 dígitos · CE: 9 dígitos"
            
        )
        self.campo_numero_documento.grid(row=6, column=0, sticky="ew")

        ctk.CTkLabel(contenedor, text="Dirección", anchor="w").grid(
            row=7, column=0, sticky="w", pady=(14, 2)
        )
        self.campo_direccion = ctk.CTkEntry(contenedor, placeholder_text="Opcional")
        self.campo_direccion.grid(row=8, column=0, sticky="ew")

        fila_botones = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_botones.grid(row=9, column=0, sticky="ew", pady=(28, 0))
        fila_botones.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            fila_botones, text="Cancelar", fg_color="gray", command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            fila_botones, text="Guardar", command=self._guardar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _guardar(self):
        nombre = self.campo_nombre.get().strip()
        tipo_seleccionado = self.combo_tipo_documento.get()
        numero = self.campo_numero_documento.get().strip()
        direccion = self.campo_direccion.get().strip()

        if not nombre:
            messagebox.showerror(
                "Datos inválidos", "El nombre o razón social es obligatorio.", parent=self
            )
            return

        tipo_documento = None if tipo_seleccionado == "(Ninguno)" else tipo_seleccionado

        # Validación local rápida (la validación definitiva la hace el backend,
        # pero atajamos aquí el caso más común de olvido del usuario).
        if tipo_documento and not numero:
            messagebox.showerror(
                "Datos inválidos",
                f"Indicaste tipo de documento '{tipo_documento}' pero no el número.",
                parent=self,
            )
            return
        if numero and not tipo_documento:
            messagebox.showerror(
                "Datos inválidos",
                "Indicaste un número de documento pero no el tipo (DNI o RUC).",
                parent=self,
            )
            return

        payload = {
            "tipo_documento": tipo_documento,
            "numero_documento": numero or None,
            "nombre_o_razon_social": nombre,
            "direccion": direccion or None,
        }

        try:
            cliente_creado = self.api.crear_cliente(payload)
        except ApiError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return

        messagebox.showinfo("Listo", "Cliente registrado correctamente.", parent=self)
        self.on_guardado(cliente_creado)
        self.destroy()
