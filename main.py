from fastapi import FastAPI

from database import get_connection
from routes.auth import router as auth_router
from routes.ubicaciones import router as ubicaciones_router
from routes.actividades import router as actividades_router
from routes.clima import router as clima_router
from routes.evaluaciones import router as evaluaciones_router

app = FastAPI(
    title="Atmos API",
    description="API del planificador de actividades Atmos",
    version="1.0.0"
)


# Rutas de autenticación
app.include_router(auth_router)
#rutas de ubicacion
app.include_router(ubicaciones_router)
#rutas de actividades
app.include_router(actividades_router)
#ruta para clima
app.include_router(clima_router)
# rutas para evaluar el clima
app.include_router(evaluaciones_router)

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