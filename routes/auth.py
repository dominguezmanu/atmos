import os
import jwt

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
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