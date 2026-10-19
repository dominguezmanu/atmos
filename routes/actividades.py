from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator
from psycopg2.extras import RealDictCursor
from database import get_connection
from routes.ubicaciones import obtener_id_usuario
from datetime import date
from fastapi import Query

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

# EDITAR ACTIVIDAD

@router.put("/{id_actividad}")
def editar_actividad(
    id_actividad: int,
    datos: ActividadDatos,
    id_usuario: int = Depends(obtener_id_usuario)
):
    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        # Verificar que la actividad pertenezca al usuario
        cursor.execute(
            """
            SELECT a.id_ubicacion
            FROM actividades a
            INNER JOIN ubicaciones u
                ON a.id_ubicacion = u.id_ubicacion
            WHERE a.id_actividad = %s
              AND u.id_usuario = %s;
            """,
            (id_actividad, id_usuario)
        )

        actividad = cursor.fetchone()

        if actividad is None:
            raise HTTPException(
                status_code=404,
                detail="Actividad no encontrada"
            )

        # Bloquear las ubicaciones involucradas durante la edición
        ubicaciones = sorted({
            actividad[0],
            datos.id_ubicacion
        })

        cursor.execute(
            """
            SELECT id_ubicacion
            FROM ubicaciones
            WHERE id_usuario = %s
              AND id_ubicacion = ANY(%s)
            ORDER BY id_ubicacion
            FOR UPDATE;
            """,
            (id_usuario, ubicaciones)
        )

        ubicaciones_validas = {
            fila[0] for fila in cursor.fetchall()
        }

        if len(ubicaciones_validas) != len(ubicaciones):
            raise HTTPException(
                status_code=404,
                detail="Ubicación no encontrada"
            )

        # Verificar conflictos excluyendo la actividad actual
        cursor.execute(
            """
            SELECT id_actividad
            FROM actividades
            WHERE id_ubicacion = %s
              AND id_actividad <> %s
              AND estado = 'pendiente'
              AND fecha_inicio < %s
              AND fecha_fin > %s;
            """,
            (
                datos.id_ubicacion,
                id_actividad,
                datos.fecha_fin,
                datos.fecha_inicio
            )
        )

        if cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Ya existe otra actividad programada "
                    "en esta ubicación durante ese horario"
                )
            )

        # Actualizar datos generales
        cursor.execute(
            """
            UPDATE actividades
            SET id_ubicacion = %s,
                titulo = %s,
                descripcion = %s,
                fecha_inicio = %s,
                fecha_fin = %s,
                tipo = %s
            WHERE id_actividad = %s;
            """,
            (
                datos.id_ubicacion,
                datos.titulo,
                datos.descripcion,
                datos.fecha_inicio,
                datos.fecha_fin,
                datos.tipo,
                id_actividad
            )
        )

        # Actualizar condiciones climáticas
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
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id_actividad)
            DO UPDATE SET
                temperatura_min = EXCLUDED.temperatura_min,
                temperatura_max = EXCLUDED.temperatura_max,
                lluvia_max = EXCLUDED.lluvia_max,
                viento_max = EXCLUDED.viento_max;
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
            "mensaje": "Actividad actualizada correctamente"
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()
        conexion.close()

# ELIMINAR ACTIVIDAD

@router.delete("/{id_actividad}")
def eliminar_actividad(
    id_actividad: int,
    id_usuario: int = Depends(obtener_id_usuario)
):
    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM actividades
            WHERE id_actividad = %s
              AND id_ubicacion IN (
                  SELECT id_ubicacion
                  FROM ubicaciones
                  WHERE id_usuario = %s
              )
            RETURNING id_actividad;
            """,
            (id_actividad, id_usuario)
        )

        resultado = cursor.fetchone()

        if resultado is None:
            raise HTTPException(
                status_code=404,
                detail="Actividad no encontrada"
            )

        conexion.commit()

        return {
            "mensaje": "Actividad eliminada correctamente"
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()
        conexion.close()
# CONSULTAR ACTIVIDADES PENDIENTES

@router.get("/pendientes")
def listar_actividades_pendientes(
    fecha: date | None = None,
    id_ubicacion: int | None = Query(default=None, ge=1),
    id_usuario: int = Depends(obtener_id_usuario)
):
    conexion = get_connection()

    cursor = conexion.cursor(
        cursor_factory=RealDictCursor
    )

    try:
        consulta = """
            SELECT
                a.id_actividad,
                a.id_ubicacion,
                u.nombre AS ubicacion,
                u.latitud,
                u.longitud,
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
              AND a.estado = 'pendiente'
        """

        parametros = [id_usuario]

        # Filtrar por fecha en horario de Guatemala
        if fecha is not None:
            consulta += """
                AND (
                    a.fecha_inicio
                    AT TIME ZONE 'America/Guatemala'
                )::date = %s
            """
            parametros.append(fecha)

        # Filtrar por ubicación
        if id_ubicacion is not None:
            consulta += """
                AND a.id_ubicacion = %s
            """
            parametros.append(id_ubicacion)

        consulta += """
            ORDER BY a.fecha_inicio ASC;
        """

        cursor.execute(consulta, parametros)

        actividades = cursor.fetchall()

        return {
            "total": len(actividades),
            "actividades": [
                dict(actividad)
                for actividad in actividades
            ]
        }

    finally:
        cursor.close()
        conexion.close()