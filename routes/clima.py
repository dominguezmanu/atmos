from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_connection
from routes.ubicaciones import obtener_id_usuario
from services.weather_service import obtener_pronostico



router = APIRouter(
    prefix="/clima",
    tags=["Clima"]
)


@router.get("/ubicacion/{id_ubicacion}")
def consultar_clima(
    id_ubicacion: int,
    horas: int = Query(default=24, ge=1, le=240),
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
                id_ubicacion,
                nombre,
                latitud,
                longitud
            FROM ubicaciones
            WHERE id_ubicacion = %s
              AND id_usuario = %s;
            """,
            (id_ubicacion, id_usuario)
        )

        ubicacion = cursor.fetchone()

        if ubicacion is None:
            raise HTTPException(
                status_code=404,
                detail="Ubicación no encontrada"
            )

    finally:
        cursor.close()
        conexion.close()

    resultado = obtener_pronostico(
        float(ubicacion["latitud"]),
        float(ubicacion["longitud"]),
        horas
    )

    return {
        "ubicacion": ubicacion["nombre"],
        **resultado
    }