"""
views/login.py
---------------
Pantalla de inicio de sesión Y de registro de usuario, combinadas en un
mismo CTkFrame. Es lo primero que ve cualquier usuario al abrir la
aplicación -- nada del sistema (productos, clientes, ventas) es accesible
sin antes autenticarse aquí.

Estructura interna:
    LoginFrame (contenedor fijo: título + tarjeta)
        └── self.contenido_actual: o bien...
            - _construir_vista_login()   (usuario/contraseña + "Crear usuario")
            - _construir_vista_registro() (formulario de alta + "Ya tengo cuenta")

    Se cambia entre ambas destruyendo y reconstruyendo únicamente el
    contenido de la tarjeta (no toda la ventana), por lo que nunca se abre
    un programa ni una ventana nueva -- todo ocurre dentro de la misma
    pantalla, tal como lo pide el flujo:

        Login -> "¿No tienes cuenta? Crear usuario" -> Registro
              -> Guardar -> vuelve a Login (con el usuario ya escrito)
"""

from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from api_client import ApiClient, ApiError


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, on_login_exitoso: Callable[[dict], None], **kwargs):
        super().__init__(master, fg_color=("gray95", "gray10"), **kwargs)
        self.api = api
        self.on_login_exitoso = on_login_exitoso

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tarjeta = ctk.CTkFrame(self, corner_radius=16, width=380)
        self.tarjeta.grid(row=0, column=0)
        self.tarjeta.grid_columnconfigure(0, weight=1)

        self._mostrar_login()

    # -----------------------------------------------------------------
    # Utilidad: limpiar la tarjeta para reconstruir su contenido
    # -----------------------------------------------------------------

    def _limpiar_tarjeta(self):
        # Cancela cualquier `self.after(...)` pendiente (típicamente un
        # `.focus()` diferido) antes de destruir los widgets a los que
        # apuntaba -- si no, al dispararse más tarde intentaría enfocar un
        # widget que ya no existe y lanzaría un TclError en la consola.
        pending_after_id = getattr(self, "_after_id_pendiente", None)
        if pending_after_id is not None:
            try:
                self.after_cancel(pending_after_id)
            except ValueError:
                pass
            self._after_id_pendiente = None

        for widget in self.tarjeta.winfo_children():
            widget.destroy()

    # ===================================================================
    # VISTA: Iniciar sesión
    # ===================================================================

    def _mostrar_login(self, username_prellenado: str = ""):
        self._limpiar_tarjeta()

        ctk.CTkLabel(
            self.tarjeta, text="📚 Papelería POS", font=ctk.CTkFont(size=24, weight="bold")
        ).grid(row=0, column=0, padx=40, pady=(36, 4))

        ctk.CTkLabel(
            self.tarjeta, text="Inicia sesión para continuar", text_color=("gray30", "gray70")
        ).grid(row=1, column=0, padx=40, pady=(0, 24))

        ctk.CTkLabel(self.tarjeta, text="Usuario", anchor="w").grid(
            row=2, column=0, padx=40, sticky="ew", pady=(0, 2)
        )
        self.campo_usuario = ctk.CTkEntry(self.tarjeta, placeholder_text="ej: admin")
        self.campo_usuario.grid(row=3, column=0, padx=40, sticky="ew")
        if username_prellenado:
            self.campo_usuario.insert(0, username_prellenado)
        self.campo_usuario.bind("<Return>", lambda _evt: self.campo_password.focus())

        ctk.CTkLabel(self.tarjeta, text="Contraseña", anchor="w").grid(
            row=4, column=0, padx=40, sticky="ew", pady=(14, 2)
        )
        self.campo_password = ctk.CTkEntry(self.tarjeta, show="•")
        self.campo_password.grid(row=5, column=0, padx=40, sticky="ew")
        self.campo_password.bind("<Return>", lambda _evt: self._iniciar_sesion())

        self.label_error = ctk.CTkLabel(
            self.tarjeta, text="", text_color="#d64545", wraplength=300, justify="left"
        )
        self.label_error.grid(row=6, column=0, padx=40, pady=(12, 0), sticky="ew")

        self.boton_ingresar = ctk.CTkButton(
            self.tarjeta, text="Iniciar sesión", height=38, command=self._iniciar_sesion
        )
        self.boton_ingresar.grid(row=7, column=0, padx=40, pady=(18, 10), sticky="ew")

        enlace_crear = ctk.CTkButton(
            self.tarjeta,
            text="¿No tienes cuenta? Crear usuario",
            fg_color="transparent",
            text_color=("gray30", "gray70"),
            hover_color=("gray90", "gray20"),
            height=28,
            command=self._mostrar_registro,
        )
        enlace_crear.grid(row=8, column=0, padx=40, pady=(0, 32), sticky="ew")

        if username_prellenado:
            self._after_id_pendiente = self.after(100, self.campo_password.focus)
        else:
            self._after_id_pendiente = self.after(100, self.campo_usuario.focus)

    def _iniciar_sesion(self):
        username = self.campo_usuario.get().strip()
        password = self.campo_password.get()

        if not username or not password:
            self.label_error.configure(text="Ingresa tu usuario y contraseña.")
            return

        self.label_error.configure(text="")
        self.boton_ingresar.configure(state="disabled", text="Ingresando...")
        self.update_idletasks()

        try:
            usuario = self.api.login(username, password)
        except ApiError as exc:
            self.label_error.configure(text=str(exc))
            self.campo_password.delete(0, "end")
            return
        finally:
            self.boton_ingresar.configure(state="normal", text="Iniciar sesión")

        self.on_login_exitoso(usuario)

    # ===================================================================
    # VISTA: Crear usuario
    # ===================================================================

    def _mostrar_registro(self):
        self._limpiar_tarjeta()

        ctk.CTkLabel(
            self.tarjeta, text="Crear usuario", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, padx=40, pady=(30, 4), sticky="w")

        ctk.CTkLabel(
            self.tarjeta,
            text="Todos los campos con * son obligatorios.",
            text_color=("gray30", "gray70"),
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, padx=40, pady=(0, 16), sticky="w")

        fila = 2

        ctk.CTkLabel(self.tarjeta, text="Nombre completo *", anchor="w").grid(
            row=fila, column=0, padx=40, sticky="ew", pady=(0, 2)
        )
        fila += 1
        self.campo_reg_nombre = ctk.CTkEntry(self.tarjeta)
        self.campo_reg_nombre.grid(row=fila, column=0, padx=40, sticky="ew")
        fila += 1

        ctk.CTkLabel(self.tarjeta, text="Usuario * (sin espacios)", anchor="w").grid(
            row=fila, column=0, padx=40, sticky="ew", pady=(14, 2)
        )
        fila += 1
        self.campo_reg_usuario = ctk.CTkEntry(self.tarjeta)
        self.campo_reg_usuario.grid(row=fila, column=0, padx=40, sticky="ew")
        fila += 1

        ctk.CTkLabel(self.tarjeta, text="Contraseña * (mínimo 6 caracteres)", anchor="w").grid(
            row=fila, column=0, padx=40, sticky="ew", pady=(14, 2)
        )
        fila += 1
        self.campo_reg_password = ctk.CTkEntry(self.tarjeta, show="•")
        self.campo_reg_password.grid(row=fila, column=0, padx=40, sticky="ew")
        fila += 1

        ctk.CTkLabel(self.tarjeta, text="Confirmar contraseña *", anchor="w").grid(
            row=fila, column=0, padx=40, sticky="ew", pady=(14, 2)
        )
        fila += 1
        self.campo_reg_password2 = ctk.CTkEntry(self.tarjeta, show="•")
        self.campo_reg_password2.grid(row=fila, column=0, padx=40, sticky="ew")
        fila += 1

        ctk.CTkLabel(self.tarjeta, text="Rol *", anchor="w").grid(
            row=fila, column=0, padx=40, sticky="ew", pady=(14, 2)
        )
        fila += 1
        self.combo_reg_rol = ctk.CTkComboBox(
            self.tarjeta, values=["Cajero", "Administrador"], state="readonly",
            command=self._al_cambiar_rol_registro,
        )
        self.combo_reg_rol.set("Cajero")
        self.combo_reg_rol.grid(row=fila, column=0, padx=40, sticky="ew")
        fila += 1

        # --- Bloque de autorización de administrador (oculto salvo que
        #     se elija rol Administrador y ya existan usuarios) ---
        self.fila_autorizacion = fila
        self.marco_autorizacion = ctk.CTkFrame(self.tarjeta, fg_color="transparent")
        self.marco_autorizacion.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.marco_autorizacion,
            text="Crear otro Administrador requiere autorización:",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
            wraplength=300,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(self.marco_autorizacion, text="Usuario administrador", anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(0, 2)
        )
        self.campo_admin_usuario = ctk.CTkEntry(self.marco_autorizacion)
        self.campo_admin_usuario.grid(row=2, column=0, sticky="ew")

        ctk.CTkLabel(self.marco_autorizacion, text="Contraseña administrador", anchor="w").grid(
            row=3, column=0, sticky="ew", pady=(10, 2)
        )
        self.campo_admin_password = ctk.CTkEntry(self.marco_autorizacion, show="•")
        self.campo_admin_password.grid(row=4, column=0, sticky="ew")

        # No se muestra por defecto: se decide tras consultar al backend
        # si ya existe algún usuario (ver _al_cambiar_rol_registro).
        fila += 1

        self.label_reg_error = ctk.CTkLabel(
            self.tarjeta, text="", text_color="#d64545", wraplength=300, justify="left"
        )
        self.label_reg_error.grid(row=fila, column=0, padx=40, pady=(14, 0), sticky="ew")
        fila += 1

        self.boton_reg_guardar = ctk.CTkButton(
            self.tarjeta, text="Guardar", height=38, command=self._crear_usuario
        )
        self.boton_reg_guardar.grid(row=fila, column=0, padx=40, pady=(16, 10), sticky="ew")
        fila += 1

        enlace_volver = ctk.CTkButton(
            self.tarjeta,
            text="¿Ya tienes cuenta? Iniciar sesión",
            fg_color="transparent",
            text_color=("gray30", "gray70"),
            hover_color=("gray90", "gray20"),
            height=28,
            command=self._mostrar_login,
        )
        enlace_volver.grid(row=fila, column=0, padx=40, pady=(0, 30), sticky="ew")

        # Consultamos una sola vez, al abrir el formulario, si ya existe
        # algún usuario en el sistema -- determina si "Administrador"
        # pedirá autorización o no.
        self._hay_usuarios = None
        self.after(50, self._consultar_si_hay_usuarios)
        self._after_id_pendiente = self.after(100, self.campo_reg_nombre.focus)

    def _consultar_si_hay_usuarios(self):
        try:
            hay_usuarios = self.api.existe_algun_usuario()
        except ApiError:
            # Si el backend no responde, asumimos que sí hay usuarios (la
            # opción más segura: pedir autorización de todas formas).
            hay_usuarios = True

        # Defensivo: si el usuario ya volvió a la pantalla de login antes de
        # que esta respuesta llegara, los widgets de registro ya no existen.
        if not self.winfo_exists() or not hasattr(self, "combo_reg_rol"):
            return
        try:
            self.combo_reg_rol.winfo_exists()
        except Exception:
            return

        self._hay_usuarios = hay_usuarios
        self._al_cambiar_rol_registro(self.combo_reg_rol.get())

    def _al_cambiar_rol_registro(self, valor_seleccionado: str):
        mostrar_autorizacion = (valor_seleccionado == "Administrador") and bool(self._hay_usuarios)
        if mostrar_autorizacion:
            self.marco_autorizacion.grid(
                row=self.fila_autorizacion, column=0, padx=40, sticky="ew", pady=(10, 0)
            )
        else:
            self.marco_autorizacion.grid_forget()

    def _crear_usuario(self):
        nombre_completo = self.campo_reg_nombre.get().strip()
        username = self.campo_reg_usuario.get().strip()
        password = self.campo_reg_password.get()
        password2 = self.campo_reg_password2.get()
        rol = "ADMIN" if self.combo_reg_rol.get() == "Administrador" else "CAJERO"

        if not nombre_completo or not username or not password:
            self.label_reg_error.configure(text="Completa todos los campos obligatorios.")
            return
        if " " in username:
            self.label_reg_error.configure(text="El usuario no puede contener espacios.")
            return
        if len(password) < 6:
            self.label_reg_error.configure(text="La contraseña debe tener al menos 6 caracteres.")
            return
        if password != password2:
            self.label_reg_error.configure(text="Las contraseñas no coinciden.")
            return

        payload = {
            "username": username,
            "password": password,
            "confirmar_password": password2,
            "nombre_completo": nombre_completo,
            "rol": rol,
        }

        if rol == "ADMIN" and self._hay_usuarios:
            admin_usuario = self.campo_admin_usuario.get().strip()
            admin_password = self.campo_admin_password.get()
            if not admin_usuario or not admin_password:
                self.label_reg_error.configure(
                    text="Ingresa el usuario y la contraseña de un administrador existente."
                )
                return
            payload["admin_username"] = admin_usuario
            payload["admin_password"] = admin_password

        self.label_reg_error.configure(text="")
        self.boton_reg_guardar.configure(state="disabled", text="Guardando...")
        self.update_idletasks()

        try:
            self.api.registrar_usuario(payload)
        except ApiError as exc:
            self.label_reg_error.configure(text=str(exc))
            return
        finally:
            self.boton_reg_guardar.configure(state="normal", text="Guardar")

        messagebox.showinfo(
            "Usuario creado",
            f"El usuario '{username}' se creó correctamente. Ahora puedes iniciar sesión.",
            parent=self,
        )
        self._mostrar_login(username_prellenado=username)
