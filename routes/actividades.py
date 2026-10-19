from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator
from psycopg2.extras import RealDictCursor

from database import get_connection
from routes.ubicaciones import obtener_id_usuario


router = APIRouter(
    prefix="/actividades",
    tags=["Actividades"]
)


# MODELO DE ACTIVIDAD

class ActividadDatos(BaseModel):
    id_ubicacion: int
    titulo: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None

    fecha_inicio: datetime
    fecha_fin: datetime

    tipo: str

    temperatura_min: float | None = None
    temperatura_max: float | None = None
    lluvia_max: float | None = Field(default=None, ge=0, le=100)
    viento_max: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validar_datos(self):

        if (
            self.fecha_inicio.tzinfo is None
            or self.fecha_fin.tzinfo is None
        ):
            raise ValueError(
                "Las fechas deben incluir zona horaria"
            )

        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError(
                "La fecha de finalización debe ser posterior al inicio"
            )

        if self.tipo not in ("interior", "exterior"):
            raise ValueError(
                "El tipo debe ser interior o exterior"
            )

        if (
            self.temperatura_min is not None
            and self.temperatura_max is not None
            and self.temperatura_min > self.temperatura_max
        ):
            raise ValueError(
                "La temperatura mínima no puede superar la máxima"
            )

        return self


# REGISTRAR ACTIVIDAD

@router.post("", status_code=201)
def crear_actividad(
    datos: ActividadDatos,
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:

        # Verificar que la ubicación pertenezca al usuario
        cursor.execute(
            """
            SELECT id_ubicacion
            FROM ubicaciones
            WHERE id_ubicacion = %s
            AND id_usuario = %s
            FOR UPDATE;
            """,
            (datos.id_ubicacion, id_usuario)
        )

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Ubicación no encontrada"
            )

        # Comprobar conflictos de horario
        cursor.execute(
            """
            SELECT id_actividad
            FROM actividades
            WHERE id_ubicacion = %s
            AND estado = 'pendiente'
            AND fecha_inicio < %s
            AND fecha_fin > %s;
            """,
            (
                datos.id_ubicacion,
                datos.fecha_fin,
                datos.fecha_inicio
            )
        )

        if cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Ya existe una actividad programada "
                    "en esta ubicación durante ese horario"
                )
            )

        # Insertar actividad
        cursor.execute(
            """
            INSERT INTO actividades
            (
                id_ubicacion,
                titulo,
                descripcion,
                fecha_inicio,
                fecha_fin,
                tipo
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_actividad;
            """,
            (
                datos.id_ubicacion,
                datos.titulo,
                datos.descripcion,
                datos.fecha_inicio,
                datos.fecha_fin,
                datos.tipo
            )
        )

        id_actividad = cursor.fetchone()[0]

        # Guardar condiciones climáticas
        cursor.execute(
            """
            INSERT INTO condiciones_actividad
            (
                id_actividad,
                temperatura_min,
                temperatura_max,
                lluvia_max,
                viento_max
            )
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                id_actividad,
                datos.temperatura_min,
                datos.temperatura_max,
                datos.lluvia_max,
                datos.viento_max
            )
        )

        conexion.commit()

        return {
            "mensaje": "Actividad registrada correctamente",
            "id_actividad": id_actividad
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()
        conexion.close()


# LISTAR ACTIVIDADES

@router.get("")
def listar_actividades(
    id_usuario: int = Depends(obtener_id_usuario)
):

    conexion = get_connection()

    cursor = conexion.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cursor.execute(
            """
            SELECT
                a.id_actividad,
                a.id_ubicacion,
                u.nombre AS ubicacion,
                a.titulo,
                a.descripcion,
                a.fecha_inicio,
                a.fecha_fin,
                a.tipo,
                a.estado,
                c.temperatura_min,
                c.temperatura_max,
                c.lluvia_max,
                c.viento_max

            FROM actividades a

            INNER JOIN ubicaciones u
                ON a.id_ubicacion = u.id_ubicacion

            LEFT JOIN condiciones_actividad c
                ON a.id_actividad = c.id_actividad

            WHERE u.id_usuario = %s

            ORDER BY a.fecha_inicio ASC;
            """,
            (id_usuario,)
        )

        actividades = cursor.fetchall()

        return [dict(fila) for fila in actividades]

    finally:
        cursor.close()
        conexion.close()