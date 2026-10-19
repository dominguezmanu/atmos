import math
from datetime import datetime, timedelta, timezone

from services.weather_service import obtener_pronostico


def convertir_fecha(fecha):
    if isinstance(fecha, datetime):
        return fecha.astimezone(timezone.utc)

    return datetime.fromisoformat(
        fecha.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def evaluar_actividad(actividad):

    inicio = convertir_fecha(actividad["fecha_inicio"])
    fin = convertir_fecha(actividad["fecha_fin"])

    ahora = datetime.now(timezone.utc)

    def sin_pronostico(motivo):
        return {
            "estado_clima": "sin_pronostico",
            "recomendacion": motivo,
            "motivos": [motivo],
            "resumen_clima": None
        }

    # No evaluar actividades que ya comenzaron
    if inicio < ahora:
        return sin_pronostico(
            "La actividad ya comenzó o su fecha pasó."
        )

    # Comprobar el período máximo disponible
    if inicio >= ahora + timedelta(hours=240):
        return sin_pronostico(
            "La actividad está fuera de los próximos 10 días."
        )

    # Solicitar únicamente las horas necesarias
    horas = min(
        240,
        max(
            1,
            math.ceil((fin - ahora).total_seconds() / 3600) + 1
        )
    )

    resultado = obtener_pronostico(
        float(actividad["latitud"]),
        float(actividad["longitud"]),
        horas
    )

    pronosticos = resultado["pronosticos"]

    # Seleccionar las horas que coinciden con la actividad
    horas_actividad = []

    for pronostico in pronosticos:

        fecha_texto = pronostico.get("fecha")

        if not fecha_texto:
            continue

        fecha = convertir_fecha(fecha_texto)
        fin_hora = fecha + timedelta(hours=1)

        if fecha < fin and fin_hora > inicio:
            horas_actividad.append({
                **pronostico,
                "_inicio": fecha,
                "_fin": fin_hora
            })

    horas_actividad.sort(key=lambda h: h["_inicio"])

    if not horas_actividad:
        return sin_pronostico(
            "No hay pronósticos para el horario de esta actividad."
        )

    # Verificar cobertura del horario completo
    cobertura = inicio

    for hora in horas_actividad:

        if hora["_inicio"] > cobertura:
            break

        if hora["_fin"] > cobertura:
            cobertura = hora["_fin"]

        if cobertura >= fin:
            break

    if cobertura < fin:
        return sin_pronostico(
            "No hay pronósticos suficientes para evaluar "
            "toda la duración de la actividad."
        )

    temperaturas = []
    lluvias = []
    vientos = []

    for hora in horas_actividad:

        temperatura = hora.get("temperatura")
        lluvia = hora.get("probabilidad_lluvia")
        viento = hora.get("velocidad_viento")

        if temperatura is not None:
            temperaturas.append(float(temperatura))

        if lluvia is not None:
            lluvias.append(float(lluvia))

        if viento is not None:
            vientos.append(float(viento))

    # Verificar datos necesarios
    condiciones = {
        "temperatura_min": "temperatura",
        "temperatura_max": "temperatura",
        "lluvia_max": "probabilidad_lluvia",
        "viento_max": "velocidad_viento"
    }

    for campo, dato_clima in condiciones.items():

        if actividad.get(campo) is not None:

            if any(
                hora.get(dato_clima) is None
                for hora in horas_actividad
            ):
                return sin_pronostico(
                    f"Faltan datos de {dato_clima} "
                    "para evaluar la actividad."
                )

    motivos = []

    temperatura_min = actividad.get("temperatura_min")
    temperatura_max = actividad.get("temperatura_max")
    lluvia_max = actividad.get("lluvia_max")
    viento_max = actividad.get("viento_max")

    # Temperatura mínima
    if temperatura_min is not None and temperaturas:

        minima = min(temperaturas)

        if minima < float(temperatura_min):
            motivos.append(
                f"La temperatura puede bajar a {minima:g} °C. "
                f"El mínimo permitido es {temperatura_min} °C."
            )

    # Temperatura máxima
    if temperatura_max is not None and temperaturas:

        maxima = max(temperaturas)

        if maxima > float(temperatura_max):
            motivos.append(
                f"La temperatura puede alcanzar {maxima:g} °C. "
                f"El máximo permitido es {temperatura_max} °C."
            )

    # Probabilidad de lluvia
    if lluvia_max is not None and lluvias:

        lluvia = max(lluvias)

        if lluvia > float(lluvia_max):
            motivos.append(
                f"La probabilidad de lluvia puede alcanzar "
                f"{lluvia:g} %. "
                f"El máximo permitido es {lluvia_max} %."
            )

    # Velocidad del viento
    if viento_max is not None and vientos:

        viento = max(vientos)

        if viento > float(viento_max):
            motivos.append(
                f"El viento puede alcanzar {viento:g} km/h. "
                f"El máximo permitido es {viento_max} km/h."
            )

    # Advertencia especial para actividades exteriores
    if actividad["tipo"] == "exterior":

        hay_tormenta = any(
            "THUNDER" in str(hora.get("condicion", "")).upper()
            for hora in horas_actividad
        )

        if hay_tormenta:
            motivos.append(
                "Se pronostican tormentas eléctricas "
                "durante la actividad."
            )

    # Generar resultado
    favorable = len(motivos) == 0

    return {
        "estado_clima": (
            "favorable" if favorable else "desfavorable"
        ),
        "recomendacion": (
            "Las condiciones meteorológicas cumplen "
            "los requisitos establecidos."
            if favorable
            else
            "Considera reprogramar la actividad "
            "debido a las condiciones meteorológicas."
        ),
        "motivos": motivos,
        "resumen_clima": {
            "temperatura_minima": (
                min(temperaturas) if temperaturas else None
            ),
            "temperatura_maxima": (
                max(temperaturas) if temperaturas else None
            ),
            "probabilidad_lluvia_maxima": (
                max(lluvias) if lluvias else None
            ),
            "velocidad_viento_maxima": (
                max(vientos) if vientos else None
            ),
            "horas_evaluadas": len(horas_actividad)
        }
    }