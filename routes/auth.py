import os
import jwt

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from psycopg2 import IntegrityError
from dotenv import load_dotenv

from database import get_connection


load_dotenv()

router = APIRouter(
    prefix="/auth",
    tags=["Autenticación"]
)

password_hash = PasswordHash.recommended()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False);

if not SECRET_KEY:
    raise RuntimeError("Falta configurar JWT_SECRET_KEY")


# MODELOS

class UsuarioRegistro(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    nombre: str = Field(min_length=1, max_length=100)
    email: EmailStr
    telefono: str | None = None
    password: str = Field(min_length=8, max_length=128)


class UsuarioLogin(BaseModel):
    username: str
    password: str

class UsuarioActualizar(BaseModel):
    nombre: str = Field(main_length=1, max_length=100)
    email: EmailStr
    telefono: str | None = None

# GENERAR TOKEN

def crear_token(id_usuario):

    expiracion = datetime.now(timezone.utc) + timedelta(hours=8)

    datos = {
        "sub": str(id_usuario),
        "exp": expiracion
    }

    token = jwt.encode(
        datos,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# REGISTRAR USUARIO

@router.post("/registro", status_code=201)
def registrar_usuario(usuario: UsuarioRegistro):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        password_protegida = password_hash.hash(
            usuario.password
        )

        cursor.execute(
            """
            INSERT INTO usuarios
            (username, nombre, email, telefono, password_hash)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_usuario, username, nombre, email;
            """,
            (
                usuario.username.strip(),
                usuario.nombre.strip(),
                str(usuario.email).lower(),
                usuario.telefono,
                password_protegida
            )
        )

        resultado = cursor.fetchone()

        conexion.commit()

        return {
            "mensaje": "Usuario registrado correctamente",
            "usuario": {
                "id_usuario": resultado[0],
                "username": resultado[1],
                "nombre": resultado[2],
                "email": resultado[3]
            }
        }

    except IntegrityError:
        conexion.rollback()

        raise HTTPException(
            status_code=409,
            detail="El usuario o correo ya está registrado"
        )

    finally:
        cursor.close()
        conexion.close()


# INICIAR SESION

@router.post("/login")
def iniciar_sesion(usuario: UsuarioLogin):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id_usuario,
                username,
                nombre,
                email,
                password_hash,
                cambio_password
            FROM usuarios
            WHERE username = %s;
            """,
            (usuario.username,)
        )

        resultado = cursor.fetchone()

        if resultado is None:
            raise HTTPException(
                status_code=401,
                detail="Usuario o contraseña incorrectos"
            )

        password_correcta = password_hash.verify(
            usuario.password,
            resultado[4]
        )

        if not password_correcta:
            raise HTTPException(
                status_code=401,
                detail="Usuario o contraseña incorrectos"
            )

        token = crear_token(resultado[0])

        return {
            "mensaje": "Inicio de sesión exitoso",
            "access_token": token,
            "token_type": "bearer",
            "cambio_password": resultado[5],
            "usuario": {
                "id_usuario": resultado[0],
                "username": resultado[1],
                "nombre": resultado[2],
                "email": resultado[3]
            }
        }

    finally:
        cursor.close()
        conexion.close()

# OBTENER USUARIO AUTENTICADO

@router.get("/me")
def obtener_usuario(
    credenciales: HTTPAuthorizationCredentials | None = Depends(security)
):

    if credenciales is None:
        raise HTTPException(
            status_code=401,
            detail="Token requerido"
        )

    try:
        datos = jwt.decode(
            credenciales.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        id_usuario = int(datos["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado"
        )

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id_usuario,
                username,
                nombre,
                email,
                telefono,
                cambio_password
            FROM usuarios
            WHERE id_usuario = %s;
            """,
            (id_usuario,)
        )

        usuario = cursor.fetchone()

        if usuario is None:
            raise HTTPException(
                status_code=401,
                detail="Usuario no encontrado"
            )

        return {
            "id_usuario": usuario[0],
            "username": usuario[1],
            "nombre": usuario[2],
            "email": usuario[3],
            "telefono": usuario[4],
            "cambio_password": usuario[5]
        }

    finally:
        cursor.close()
        conexion.close()
# ACTUALIZAR PERFIL DEL USUARIO

@router.patch("/perfil")
def actualizar_perfil(
    datos: UsuarioActualizar,
    credenciales: HTTPAuthorizationCredentials | None = Depends(security)
):

    if credenciales is None:
        raise HTTPException(
            status_code=401,
            detail="Token requerido"
        )

    try:
        token = jwt.decode(
            credenciales.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        id_usuario = int(token["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado"
        )

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            UPDATE usuarios
            SET nombre = %s,
                email = %s,
                telefono = %s
            WHERE id_usuario = %s
            RETURNING
                id_usuario,
                username,
                nombre,
                email,
                telefono;
            """,
            (
                datos.nombre.strip(),
                str(datos.email).lower(),
                datos.telefono,
                id_usuario
            )
        )

        usuario = cursor.fetchone()

        if usuario is None:
            conexion.rollback()

            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )

        conexion.commit()

        return {
            "mensaje": "Perfil actualizado correctamente",
            "usuario": {
                "id_usuario": usuario[0],
                "username": usuario[1],
                "nombre": usuario[2],
                "email": usuario[3],
                "telefono": usuario[4]
            }
        }

    except IntegrityError:
        conexion.rollback()

        raise HTTPException(
            status_code=409,
            detail="El correo electrónico ya está registrado"
        )

    finally:
        cursor.close()
        conexion.close()