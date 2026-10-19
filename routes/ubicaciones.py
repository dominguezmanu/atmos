import os
import jwt

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from database import get_connection


load_dotenv()

router = APIRouter(
    prefix="/ubicaciones",
    tags=["Ubicaciones"]
)

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"


# MODELO DE UBICACION

class UbicacionDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    direccion: str | None = None
    latitud: float = Field(ge=-90, le=90)
    longitud: float = Field(ge=-180, le=180)
    descripcion: str | None = None


# OBTENER USUARIO DEL TOKEN

def obtener_id_usuario(
    credenciales: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        datos = jwt.decode(
            credenciales.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return int(datos["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado"
        )


# REGISTRAR UBICACION

@router.post("", status_code=201)
def crear_ubicacion(
    datos: UbicacionDatos,
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO ubicaciones
            (id_usuario, nombre, direccion,
             latitud, longitud, descripcion)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_ubicacion;
            """,
            (
                id_usuario,
                datos.nombre,
                datos.direccion,
                datos.latitud,
                datos.longitud,
                datos.descripcion
            )
        )

        id_ubicacion = cursor.fetchone()[0]

        conexion.commit()

        return {
            "mensaje": "Ubicación registrada correctamente",
            "id_ubicacion": id_ubicacion
        }

    finally:
        cursor.close()
        conexion.close()


# LISTAR UBICACIONES

@router.get("")
def listar_ubicaciones(
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id_ubicacion,
                nombre,
                direccion,
                latitud,
                longitud,
                descripcion
            FROM ubicaciones
            WHERE id_usuario = %s
            ORDER BY nombre;
            """,
            (id_usuario,)
        )

        registros = cursor.fetchall()

        return [
            {
                "id_ubicacion": fila[0],
                "nombre": fila[1],
                "direccion": fila[2],
                "latitud": float(fila[3]),
                "longitud": float(fila[4]),
                "descripcion": fila[5]
            }
            for fila in registros
        ]

    finally:
        cursor.close()
        conexion.close()


# EDITAR UBICACION

@router.put("/{id_ubicacion}")
def editar_ubicacion(
    id_ubicacion: int,
    datos: UbicacionDatos,
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            UPDATE ubicaciones
            SET nombre = %s,
                direccion = %s,
                latitud = %s,
                longitud = %s,
                descripcion = %s
            WHERE id_ubicacion = %s
              AND id_usuario = %s
            RETURNING id_ubicacion;
            """,
            (
                datos.nombre,
                datos.direccion,
                datos.latitud,
                datos.longitud,
                datos.descripcion,
                id_ubicacion,
                id_usuario
            )
        )

        resultado = cursor.fetchone()

        if resultado is None:
            conexion.rollback()
            raise HTTPException(
                status_code=404,
                detail="Ubicación no encontrada"
            )

        conexion.commit()

        return {
            "mensaje": "Ubicación actualizada correctamente"
        }

    finally:
        cursor.close()
        conexion.close()


# ELIMINAR UBICACION

@router.delete("/{id_ubicacion}")
def eliminar_ubicacion(
    id_ubicacion: int,
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM ubicaciones
            WHERE id_ubicacion = %s
              AND id_usuario = %s
            RETURNING id_ubicacion;
            """,
            (id_ubicacion, id_usuario)
        )

        resultado = cursor.fetchone()

        if resultado is None:
            conexion.rollback()
            raise HTTPException(
                status_code=404,
                detail="Ubicación no encontrada"
            )

        conexion.commit()

        return {
            "mensaje": "Ubicación eliminada correctamente"
        }

    finally:
        cursor.close()
        conexion.close()