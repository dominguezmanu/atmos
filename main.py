from fastapi import FastAPI

from database import get_connection
from routes.auth import router as auth_router


app = FastAPI(
    title="Atmos API",
    description="API del planificador de actividades Atmos",
    version="1.0.0"
)


# Rutas de autenticación
app.include_router(auth_router)


@app.get("/")
def inicio():
    return {
        "aplicacion": "Atmos",
        "mensaje": "API funcionando correctamente"
    }


@app.get("/test-db")
def probar_base_datos():

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT current_database();")
        resultado = cursor.fetchone()

        return {
            "estado": "Conectado",
            "base_de_datos": resultado[0]
        }

    finally:
        cursor.close()
        conexion.close()