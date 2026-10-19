from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

from database import get_connection
from routes.ubicaciones import obtener_id_usuario
from services.evaluacion_service import evaluar_actividad


router = APIRouter(
    prefix="/evaluaciones",
    tags=["Evaluaciones meteorológicas"]
)


@router.get("/actividad/{id_actividad}")
def consultar_evaluacion(
    id_actividad: int,
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
                a.titulo,
                a.descripcion,
                a.fecha_inicio,
                a.fecha_fin,
                a.tipo,
                a.estado,

                u.nombre AS ubicacion,
                u.latitud,
                u.longitud,

                c.temperatura_min,
                c.temperatura_max,
                c.lluvia_max,
                c.viento_max

            FROM actividades a

            INNER JOIN ubicaciones u
                ON a.id_ubicacion = u.id_ubicacion

            LEFT JOIN condiciones_actividad c
                ON a.id_actividad = c.id_actividad

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

    finally:
        cursor.close()
        conexion.close()

    evaluacion = evaluar_actividad(actividad)

    return {
        "id_actividad": actividad["id_actividad"],
        "actividad": actividad["titulo"],
        "ubicacion": actividad["ubicacion"],
        "fecha_inicio": actividad["fecha_inicio"],
        "fecha_fin": actividad["fecha_fin"],
        **evaluacion
    }