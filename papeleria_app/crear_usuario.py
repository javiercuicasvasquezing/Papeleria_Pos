"""
crear_usuario.py
------------------
Script de línea de comandos para crear un usuario directamente en la base
de datos, sin pasar por la API.

¿Por qué existe este script si ya hay un endpoint POST /usuarios/?
    Porque ese endpoint exige estar autenticado como administrador -- y para
    poder iniciar sesión por primera vez, necesitas que exista al menos un
    usuario administrador. Este script resuelve ese "problema del huevo y
    la gallina": es la forma de crear el primer usuario del sistema.

    Una vez que tengas tu primer administrador, puedes seguir usando este
    mismo script para crear más usuarios (por comodidad), o usar el
    endpoint POST /usuarios/ desde una futura pantalla de "Gestión de
    usuarios" en la interfaz de escritorio.

Uso:
    python crear_usuario.py
"""

import getpass

from database import SessionLocal, init_db
from migraciones import ejecutar_migraciones
from models import RolUsuario, Usuario
from security import hash_password


def main():
    ejecutar_migraciones()
    init_db()
    db = SessionLocal()

    print("=== Crear nuevo usuario — Sistema POS Librería/Papelería ===\n")

    username = input("Nombre de usuario (sin espacios, para iniciar sesión): ").strip().lower()
    if not username:
        print("El nombre de usuario no puede estar vacío. Cancelado.")
        return
    if " " in username:
        print("El nombre de usuario no puede contener espacios. Cancelado.")
        return
    if db.query(Usuario).filter(Usuario.username == username).first():
        print(f"Ya existe un usuario con el nombre '{username}'. Cancelado.")
        return

    nombre_completo = input("Nombre completo: ").strip() or username

    while True:
        password = getpass.getpass("Contraseña (mínimo 6 caracteres, no se muestra en pantalla): ")
        if len(password) < 6:
            print("La contraseña debe tener al menos 6 caracteres. Intenta de nuevo.\n")
            continue
        confirmacion = getpass.getpass("Confirma la contraseña: ")
        if password != confirmacion:
            print("Las contraseñas no coinciden. Intenta de nuevo.\n")
            continue
        break

    es_admin = input("¿Es administrador? (s/n): ").strip().lower().startswith("s")
    rol = RolUsuario.ADMIN if es_admin else RolUsuario.CAJERO

    nuevo_usuario = Usuario(
        username=username,
        password_hash=hash_password(password),
        nombre_completo=nombre_completo,
        rol=rol,
        activo=True,
    )
    db.add(nuevo_usuario)
    db.commit()

    print(f"\n✅ Usuario '{username}' creado correctamente con rol {rol.value}.")
    print("Ya puedes iniciar sesión con estas credenciales en la aplicación de escritorio.")


if __name__ == "__main__":
    main()
