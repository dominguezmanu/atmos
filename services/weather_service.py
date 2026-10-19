import os
import requests

from fastapi import HTTPException


WEATHER_URL = (
    "https://weather.googleapis.com/v1/forecast/hours:lookup"
)


def obtener_pronostico(latitud: float, longitud: float):

    api_key = os.getenv("GOOGLE_WEATHER_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Weather API no está configurada"
        )

    parametros = {
        "key": api_key,
        "location.latitude": latitud,
        "location.longitude": longitud,
        "hours": 24,
        "pageSize": 24,
        "unitsSystem": "METRIC",
        "languageCode": "es"
    }

    try:
        respuesta = requests.get(
            WEATHER_URL,
            params=parametros,
            timeout=20
        )

        respuesta.raise_for_status()

        datos = respuesta.json()

    except requests.exceptions.RequestException:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar Google Weather API"
        )

    pronosticos = []

    for hora in datos.get("forecastHours", []):

        temperatura = hora.get("temperature", {})

        precipitacion = hora.get("precipitation", {})
        probabilidad = precipitacion.get("probability", {})

        viento = hora.get("wind", {})
        velocidad = viento.get("speed", {})

        condicion = hora.get("weatherCondition", {})
        descripcion = condicion.get("description", {})

        pronosticos.append({
            "fecha": hora.get("interval", {}).get("startTime"),
            "temperatura": temperatura.get("degrees"),
            "probabilidad_lluvia": probabilidad.get("percent"),
            "velocidad_viento": velocidad.get("value"),
            "descripcion": descripcion.get("text"),
            "condicion": condicion.get("type")
        })

    return {
        "latitud": latitud,
        "longitud": longitud,
        "pronosticos": pronosticos
    }