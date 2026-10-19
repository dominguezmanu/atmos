import os
import requests

from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Atmos")


def enviar_correo(destinatario, asunto, mensaje):

    if not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        raise RuntimeError("Faltan las credenciales de Brevo")

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    datos = {
        "sender": {
            "name": BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL
        },
        "to": [
            {
                "email": destinatario
            }
        ],
        "subject": asunto,
        "textContent": mensaje
    }

    try:
        respuesta = requests.post(
            url,
            headers=headers,
            json=datos,
            timeout=15
        )

        respuesta.raise_for_status()

        return respuesta.status_code == 201

    except requests.RequestException:
        return False