import os
import requests

from fastapi import HTTPException


WEATHER_URL = (
    "https://weather.googleapis.com/v1/forecast/hours:lookup"
)


def obtener_pronostico(
    latitud: float,
    longitud: float,
    horas: int = 24
):

    api_key = os.getenv("GOOGLE_WEATHER_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Weather API no está configurada"
        )

    if not 1 <= horas <= 240:
        raise HTTPException(
            status_code=400,
            detail="Las horas deben estar entre 1 y 240"
        )

    parametros = {
        "key": api_key,
        "location.latitude": latitud,
        "location.longitude": longitud,
        "hours": horas,
        "pageSize": 24,
        "unitsSystem": "METRIC",
        "languageCode": "es"
    }

    pronosticos = []
    pagina = None

    try:
        while len(pronosticos) < horas:

            if pagina:
                parametros["pageToken"] = pagina

            respuesta = requests.get(
                WEATHER_URL,
                params=parametros,
                timeout=20
            )

            respuesta.raise_for_status()

            datos = respuesta.json()

            for hora in datos.get("forecastHours", []):

                temperatura = hora.get("temperature", {})

                precipitacion = hora.get(
                    "precipitation", {}
                )

                probabilidad = precipitacion.get(
                    "probability", {}
                )

                viento = hora.get("wind", {})
                velocidad = viento.get("speed", {})

                condicion = hora.get(
                    "weatherCondition", {}
                )

                descripcion = condicion.get(
                    "description", {}
                )

                pronosticos.append({
                    "fecha": hora.get(
                        "interval", {}
                    ).get("startTime"),

                    "temperatura": temperatura.get(
                        "degrees"
                    ),

                    "probabilidad_lluvia":
                        probabilidad.get("percent"),

                    "velocidad_viento":
                        velocidad.get("value"),

                    "descripcion":
                        descripcion.get("text"),

                    "condicion":
                        condicion.get("type")
                })

            pagina = datos.get("nextPageToken")

            if not pagina:
                break

    except requests.exceptions.RequestException:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar Google Weather API"
        )

    return {
        "latitud": latitud,
        "longitud": longitud,
        "horas_solicitadas": horas,
        "total_pronosticos": len(pronosticos),
        "pronosticos": pronosticos[:horas]
    }