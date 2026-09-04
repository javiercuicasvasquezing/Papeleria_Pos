"""
api_client.py
-------------
Capa de comunicación entre la interfaz de escritorio (CustomTkinter) y el
backend FastAPI del Sistema POS de Librería/Papelería.

Este módulo es el equivalente, en el lado de la interfaz, al "Service Layer"
que probablemente ya usas en SPYDER INV PRO: ninguna pantalla (vista) le
habla directamente a `requests`; todas pasan por `ApiClient`. Esto tiene dos
ventajas prácticas:
    1. Si el día de mañana cambias la URL del servidor, el puerto, o incluso
       la forma de autenticarte, solo tocas este archivo.
    2. Los errores de red o del servidor se traducen aquí UNA sola vez a
       mensajes en español entendibles para el usuario final (el vendedor de
       la papelería), en vez de que cada pantalla tenga que lidiar con
       excepciones de `requests` o códigos HTTP crudos.

Uso típico desde una pantalla:
    from api_client import ApiClient, ApiError

    api = ApiClient()
    try:
        productos = api.listar_productos()
    except ApiError as e:
        mostrar_mensaje_error(str(e))
"""

from typing import Any, Optional

import requests

# URL base del backend local. Si en algún momento corres la API en otro
# puerto o en otra máquina de la red local, este es el único lugar que
# necesitas cambiar.
API_BASE_URL = "http://127.0.0.1:8000"

# Tiempo máximo de espera por respuesta del servidor, en segundos.
TIMEOUT_SEGUNDOS = 10


class ApiError(Exception):
    """
    Excepción única que lanza `ApiClient` ante cualquier problema:
    servidor caído, timeout, o un error de negocio devuelto por la API
    (404, 409, 422, etc). El mensaje ya viene listo para mostrarse
    directamente en un mensaje emergente (messagebox) de la interfaz.
    """
    pass


class SesionExpirada(ApiError):
    """
    Subclase específica de ApiError para respuestas 401 (no autenticado /
    sesión inválida o expirada). Se distingue del resto de los errores para
    que la interfaz pueda reaccionar de forma especial: cerrar la sesión
    local y devolver al usuario a la pantalla de inicio de sesión, en vez de
    solo mostrar un mensaje de error genérico.
    """
    pass


class ApiClient:
    """Cliente HTTP hacia el backend FastAPI del sistema POS."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

        # Estado de sesión: se llenan tras un login() exitoso.
        self.token: Optional[str] = None
        self.usuario_actual: Optional[dict] = None

    # -----------------------------------------------------------------
    # Núcleo interno: una sola función maneja TODAS las peticiones HTTP,
    # para no repetir manejo de errores en cada método público.
    # -----------------------------------------------------------------

    def _request(self, metodo: str, ruta: str, **kwargs) -> Any:
        url = f"{self.base_url}{ruta}"
        try:
            respuesta = self._session.request(metodo, url, timeout=TIMEOUT_SEGUNDOS, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise ApiError(
                "No se pudo conectar con el servidor local.\n\n"
                "Verifica que el backend esté corriendo (uvicorn main:app) "
                "en otra ventana antes de usar la aplicación."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ApiError(
                "El servidor tardó demasiado en responder. Intenta nuevamente."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ApiError(f"Error de conexión inesperado: {exc}") from exc

        if respuesta.status_code == 401:
            raise SesionExpirada(self._extraer_mensaje_error(respuesta))

        if respuesta.status_code >= 400:
            raise ApiError(self._extraer_mensaje_error(respuesta))

        if respuesta.status_code == 204 or not respuesta.content:
            return None

        return respuesta.json()

    @staticmethod
    def _extraer_mensaje_error(respuesta: requests.Response) -> str:
        """
        Convierte una respuesta de error de FastAPI (JSON con clave 'detail')
        en un mensaje de texto plano y legible.

        FastAPI devuelve 'detail' de dos formas distintas según el tipo de
        error:
            - str  -> errores de negocio lanzados con HTTPException (404, 409, 400...)
            - list -> errores de validación de Pydantic (422), uno por campo.
        """
        try:
            datos = respuesta.json()
        except ValueError:
            return f"Error del servidor (HTTP {respuesta.status_code})."

        detalle = datos.get("detail")

        if isinstance(detalle, str):
            return detalle

        if isinstance(detalle, list):
            mensajes = []
            for error in detalle:
                msg = error.get("msg", str(error))
                # Pydantic antepone "Value error, " a los errores de
                # @model_validator; lo quitamos para que se lea más natural.
                mensajes.append(msg.replace("Value error, ", ""))
            return "\n".join(mensajes)

        return f"Error del servidor (HTTP {respuesta.status_code})."

    # -----------------------------------------------------------------
    # Salud del servidor
    # -----------------------------------------------------------------

    def verificar_conexion(self) -> bool:
        """
        Devuelve True si el backend responde correctamente, False si no.
        No lanza ApiError: pensado para chequeos silenciosos de estado
        (ej. un indicador de "conectado / desconectado" en la interfaz).
        """
        try:
            self._request("GET", "/")
            return True
        except ApiError:
            return False

    # -----------------------------------------------------------------
    # Autenticación
    # -----------------------------------------------------------------

    def login(self, username: str, password: str) -> dict:
        """
        Inicia sesión contra el backend. Si es exitoso, guarda el token y lo
        adjunta automáticamente a TODAS las peticiones futuras de esta misma
        instancia de ApiClient (header Authorization). Devuelve los datos
        del usuario autenticado.
        """
        respuesta = self._request(
            "POST", "/auth/login", json={"username": username, "password": password}
        )
        self.token = respuesta["token"]
        self.usuario_actual = respuesta["usuario"]
        self._session.headers.update({"Authorization": f"Bearer {self.token}"})
        return self.usuario_actual

    def logout(self) -> None:
        """
        Cierra la sesión actual (avisa al backend para invalidar el token, y
        limpia el estado local). No lanza error si la llamada al backend
        falla (ej. el servidor ya no responde) -- cerrar sesión localmente
        siempre debe poder completarse.
        """
        try:
            self._request("POST", "/auth/logout")
        except ApiError:
            pass
        finally:
            self.token = None
            self.usuario_actual = None
            self._session.headers.pop("Authorization", None)

    def existe_algun_usuario(self) -> bool:
        """
        True si ya hay al menos un usuario registrado en el sistema. Lo usa
        la pantalla de "Crear usuario" para decidir si debe pedir
        credenciales de administrador al crear otro ADMIN (no aplica para
        el primer usuario del sistema).
        """
        respuesta = self._request("GET", "/auth/existe-algun-usuario")
        return bool(respuesta["hay_usuarios"])

    def registrar_usuario(self, payload: dict) -> dict:
        """
        Crea un usuario nuevo SIN necesitar sesión iniciada (endpoint
        público). Es lo que usa el botón "Crear usuario" del login.
        A diferencia de login(), esto NO inicia sesión automáticamente --
        el flujo normal es volver a la pantalla de login después.
        """
        return self._request("POST", "/auth/registro", json=payload)

    # -----------------------------------------------------------------
    # Productos (Módulo 2 de la API)
    # -----------------------------------------------------------------

    def crear_producto(self, payload: dict) -> dict:
        return self._request("POST", "/productos/", json=payload)

    def listar_productos(
        self, skip: int = 0, limit: int = 50, marca: Optional[str] = None
    ) -> dict:
        params = {"skip": skip, "limit": limit}
        if marca:
            params["marca"] = marca
        return self._request("GET", "/productos/", params=params)

    def buscar_productos(
        self, q: Optional[str] = None, codigo_barras: Optional[str] = None, limit: int = 50
    ) -> dict:
        params = {"limit": limit}
        if q:
            params["q"] = q
        if codigo_barras:
            params["codigo_barras"] = codigo_barras
        return self._request("GET", "/productos/buscar/", params=params)

    def actualizar_producto(self, producto_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/productos/{producto_id}", json=payload)

    def importar_excel_vista_previa(self, ruta_archivo: str) -> dict:
        with open(ruta_archivo, "rb") as f:
            nombre_archivo = ruta_archivo.replace("\\", "/").split("/")[-1]
            archivos = {"archivo": (nombre_archivo, f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            # IMPORTANTE: la sesión trae por defecto "Content-Type: application/json"
            # (para las peticiones normales). Para un envío de archivo (multipart)
            # ese header debe ir AUSENTE, no solo omitido -- si no se fuerza a None
            # explícitamente aquí, `requests` arrastra el de la sesión y el
            # backend no logra leer el archivo (llega mal formado).
            headers = {"Content-Type": None}
            respuesta = self._session.post(
                f"{self.base_url}/productos/importar/vista-previa",
                files=archivos, headers=headers, timeout=60,
            )
        if respuesta.status_code >= 400:
            raise ApiError(self._extraer_mensaje_error(respuesta))
        return respuesta.json()

    def importar_excel_confirmar(self, modo: str, actualizar_stock: bool, filas: list[dict]) -> dict:
        return self._request(
            "POST", "/productos/importar/confirmar",
            json={"modo": modo, "actualizar_stock": actualizar_stock, "filas": filas},
        )

    def importar_excel_reemplazar_todo(self, filas: list[dict], confirmacion: str) -> dict:
        return self._request(
            "POST", "/productos/importar/reemplazar-todo",
            json={"filas": filas, "confirmacion": confirmacion},
        )

    def eliminar_productos(self, ids: list[int]) -> dict:
        return self._request("POST", "/productos/eliminar", json={"ids": ids})

    def generar_reporte_diario(self, fecha: str) -> bytes:
        respuesta = self._session.get(f"{self.base_url}/reportes/diario", params={"fecha": fecha}, timeout=30)
        if respuesta.status_code >= 400:
            raise ApiError(self._extraer_mensaje_error(respuesta))
        return respuesta.content

    def generar_reporte_rango(self, desde: str, hasta: str) -> bytes:
        respuesta = self._session.get(
            f"{self.base_url}/reportes/rango", params={"desde": desde, "hasta": hasta}, timeout=30
        )
        if respuesta.status_code >= 400:
            raise ApiError(self._extraer_mensaje_error(respuesta))
        return respuesta.content

    def resumen_financiero(self, desde: str, hasta: str) -> dict:
        return self._request("GET", "/reportes/resumen", params={"desde": desde, "hasta": hasta})

    def exportar_excel(self, ruta_destino: str) -> None:
        respuesta = self._session.get(f"{self.base_url}/productos/exportar-excel", timeout=30)
        if respuesta.status_code >= 400:
            raise ApiError(self._extraer_mensaje_error(respuesta))
        with open(ruta_destino, "wb") as f:
            f.write(respuesta.content)

    # -----------------------------------------------------------------
    # Clientes (Módulo 3 de la API)
    # -----------------------------------------------------------------

    def crear_cliente(self, payload: dict) -> dict:
        return self._request("POST", "/clientes/", json=payload)

    def obtener_cliente_por_documento(self, documento: str) -> Optional[dict]:
        """
        Devuelve el cliente si existe, o None si no está registrado
        (en vez de dejar propagar el ApiError 404, ya que "cliente no
        encontrado" es un resultado válido y esperado en el flujo del POS,
        no un error que deba interrumpir al usuario).
        """
        try:
            return self._request("GET", f"/clientes/{documento}")
        except ApiError as exc:
            if "no existe" in str(exc).lower():
                return None
            raise

    # -----------------------------------------------------------------
    # Ventas (Módulo 4 de la API)
    # -----------------------------------------------------------------

    def crear_venta(self, payload: dict) -> dict:
        return self._request("POST", "/ventas/", json=payload)
