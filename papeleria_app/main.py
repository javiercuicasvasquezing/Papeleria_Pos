"""
main.py
-------
Punto de entrada de la API FastAPI del Sistema POS de Librería/Papelería.

Ejecutar con:
    uvicorn main:app --reload

IMPORTANTE: desde el Módulo de Autenticación, casi todos los endpoints
exigen sesión iniciada (header `Authorization: Bearer <token>`, obtenido
en POST /auth/login). Ahora puedes crear tu primer usuario administrador
directamente desde la pantalla de login de la app de escritorio (botón
"Crear usuario"), sin necesitar un programa aparte.
"""

from fastapi import FastAPI

from database import init_db
from migraciones import ejecutar_migraciones
from routers import auth, usuarios, productos, clientes, ventas, reportes

app = FastAPI(
    title="Sistema POS - Librería/Papelería",
    description="API local para gestión de inventario, clientes, ventas y usuarios (Soles - PEN).",
    version="0.6.0",
)


@app.on_event("startup")
def on_startup():
    """
    Aplica migraciones pendientes sobre datos existentes (ej. renombres de
    valores), y LUEGO crea las tablas que todavía no existan. El orden
    importa: las migraciones operan con SQL crudo sobre la base de datos
    tal como está guardada hoy, antes de que el ORM intente leerla.
    """
    ejecutar_migraciones()
    init_db()


@app.get("/", tags=["Salud"])
def health_check():
    """Endpoint simple para verificar que la API está corriendo. No requiere autenticación."""
    return {"status": "ok", "app": "Sistema POS - Librería/Papelería"}


# Registro de routers por módulo
app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(productos.router)
app.include_router(clientes.router)
app.include_router(ventas.router)
app.include_router(reportes.router)
