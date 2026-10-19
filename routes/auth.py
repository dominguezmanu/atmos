import os
import jwt
import secrets
import string

from services.email_service import enviar_correo


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

class CambioPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=128)
    confirmar_password: str

class RecuperarPassword(BaseModel):
    email: EmailStr
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
                cambio_password,
                password_temporal_expira
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
        # Verificar expiración de contraseña temporal

        if resultado[5] is True:

            expiracion = resultado[6]

        if (
            expiracion is not None
            and datetime.now(timezone.utc) >= expiracion
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "La contraseña temporal ha expirado. "
                    "Solicita una nueva."
                )
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

# CAMBIAR CONTRASEÑA

@router.post("/cambiar-password")
def cambiar_password(
    datos: CambioPassword,
    credenciales: HTTPAuthorizationCredentials | None = Depends(security)
):

    if credenciales is None:
        raise HTTPException(
            status_code=401,
            detail="Token requerido"
        )

    # Validar token JWT
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

    # Comprobar confirmación
    if datos.password_nueva != datos.confirmar_password:
        raise HTTPException(
            status_code=400,
            detail="Las contraseñas nuevas no coinciden"
        )

    if datos.password_actual == datos.password_nueva:
        raise HTTPException(
            status_code=400,
            detail="La contraseña nueva debe ser diferente a la actual"
        )

    conexion = get_connection()
    cursor = conexion.cursor()

    try:

        # Buscar contraseña actual
        cursor.execute(
            """
            SELECT password_hash
            FROM usuarios
            WHERE id_usuario = %s;
            """,
            (id_usuario,)
        )

        usuario = cursor.fetchone()

        if usuario is None:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )

        # Verificar contraseña actual
        if not password_hash.verify(
            datos.password_actual,
            usuario[0]
        ):
            raise HTTPException(
                status_code=401,
                detail="La contraseña actual es incorrecta"
            )

        # Proteger nueva contraseña
        nueva_password_hash = password_hash.hash(
            datos.password_nueva
        )

        # Actualizar contraseña
        cursor.execute(
            """
            UPDATE usuarios
            SET password_hash = %s,
                cambio_password = FALSE,
                password_temporal_expira = NULL
            WHERE id_usuario = %s;
            """,
            (
                nueva_password_hash,
                id_usuario
            )
        )

        conexion.commit()

        return {
            "mensaje": "Contraseña actualizada correctamente"
        }

    finally:
        cursor.close()
        conexion.close()
# RECUPERAR CONTRASEÑA

@router.post("/recuperar-password")
def recuperar_password(datos: RecuperarPassword):

    mensaje = {
        "mensaje": (
            "Si el correo está registrado, "
            "recibirás instrucciones de recuperación."
        )
    }

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id_usuario,
                nombre,
                email,
                ultima_recuperacion
            FROM usuarios
            WHERE LOWER(email) = %s
            FOR UPDATE;
            """,
            (str(datos.email).lower(),)
        )

        usuario = cursor.fetchone()

        # No revelar si el correo existe
        if usuario is None:
            return mensaje

        id_usuario = usuario[0]
        nombre = usuario[1]
        email = usuario[2]
        ultima_recuperacion = usuario[3]

        ahora = datetime.now(timezone.utc)

        # Esperar al menos 60 segundos entre solicitudes
        if ultima_recuperacion is not None:
            diferencia = ahora - ultima_recuperacion

            if diferencia < timedelta(seconds=60):
                return mensaje

        # Generar contraseña temporal segura
        caracteres = (
            string.ascii_letters +
            string.digits +
            "!@#$%"
        )

        password_temporal = "".join(
            secrets.choice(caracteres)
            for _ in range(14)
        )

        expiracion = ahora + timedelta(minutes=15)

        # Preparar correo
        asunto = "Atmos - Recuperación de contraseña"

        contenido = f"""
            Hola, {nombre}.

            Recibimos una solicitud para recuperar tu cuenta de Atmos.

            Tu contraseña temporal es:

            {password_temporal}

            Esta contraseña vencerá en 15 minutos.

            Cuando inicies sesión, deberás establecer una nueva contraseña.

            Si no solicitaste este cambio, contacta al administrador.

            Equipo Atmos
            """

        # Solicitar envío mediante Brevo
        enviado = enviar_correo(
            destinatario=email,
            asunto=asunto,
            mensaje=contenido
        )

        if not enviado:
            conexion.rollback()
            return mensaje

        # Proteger contraseña temporal
        hash_temporal = password_hash.hash(
            password_temporal
        )

        # Actualizar usuario
        cursor.execute(
            """
            UPDATE usuarios
            SET password_hash = %s,
                cambio_password = TRUE,
                password_temporal_expira = %s,
                ultima_recuperacion = %s
            WHERE id_usuario = %s;
            """,
            (
                hash_temporal,
                expiracion,
                ahora,
                id_usuario
            )
        )

        conexion.commit()

        return mensaje

    except Exception:
        conexion.rollback()
        raise HTTPException(
            status_code=500,
            detail="No se pudo procesar la solicitud"
        )

    finally:
        cursor.close()
        conexion.close()