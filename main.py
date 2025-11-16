from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
from datetime import datetime
import threading
import time

# Configuración
DATA_FILE = "pools.json"
app = Flask(__name__)

# Número(s) de admin fijo(s)
ADMINS = ["whatsapp:+34600111222"]  # Pon aquí tu número de WhatsApp

# Cargar y guardar datos
def cargar_datos():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"pools": [], "usuarios": []}

def guardar_datos(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = cargar_datos()

# Función para enviar notificaciones de apertura de inscripciones
def notificar_apertura():
    while True:
        now = datetime.now()
        for pool in data["pools"]:
            apertura = datetime.fromisoformat(pool["apertura_inscripciones"])
            if "notificado" not in pool and now >= apertura:
                for user in pool["interesados"]:
                    enviar_mensaje(user, f"📢 La inscripción para {pool['nombre']} ya está abierta. Envía 'apuntarme {pool['id']}' o 'apuntarme {pool['id']} +<pareja>' para unirte.")
                pool["notificado"] = True
                pool["interesados"] = []  # limpiar interesados
                guardar_datos(data)
        time.sleep(60)

# Función simulada de envío (Twilio envía desde webhook)
def enviar_mensaje(to, mensaje):
    # Aquí podrías usar la API de Twilio para enviar mensaje proactivo si tu plan lo permite
    print(f"Enviar a {to}: {mensaje}")

# Start scheduler en segundo plano
threading.Thread(target=notificar_apertura, daemon=True).start()

# Webhook principal
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    user = request.values.get("From", "")
    resp = MessagingResponse()

    global data
    data = cargar_datos()

    # Inicializar lista de usuarios si no existe
    if "usuarios" not in data:
        data["usuarios"] = []

    # Mensaje de bienvenida para usuarios nuevos
    if user not in data["usuarios"]:
        data["usuarios"].append(user)
        guardar_datos(data)
        resp.message(
            "👋 ¡Hola! Bienvenido a PoolManager.\n"
            "Aquí podrás apuntarte a pools de pádel, recibir notificaciones y ver tus horarios.\n"
            "Escribe 'ayuda' para ver todos los comandos disponibles."
        )
        return str(resp)

    # Admin
    is_admin = user in ADMINS

    # Comandos de admin
    if is_admin:
        if incoming_msg.startswith("crear_pool"):
            try:
                _, nombre, precio, horario, apertura = incoming_msg.split(" ", 4)
                pool_id = nombre.lower().replace(" ", "_")
                data["pools"].append({
                    "id": pool_id,
                    "nombre": nombre,
                    "precio": float(precio),
                    "horario": horario,
                    "apertura_inscripciones": apertura,
                    "jugadores": [],
                    "interesados": []
                })
                guardar_datos(data)
                resp.message(f"✅ Pool '{nombre}' creada con ID {pool_id}")
            except:
                resp.message("❌ Error creando pool. Usa: crear_pool <nombre> <precio> <horario> <apertura_iso>")
            return str(resp)

        elif incoming_msg.startswith("notificar"):
            try:
                _, pool_id, *mensaje = incoming_msg.split(" ")
                mensaje = " ".join(mensaje)
                pool = next((p for p in data["pools"] if p["id"]==pool_id), None)
                if not pool:
                    resp.message("❌ Pool no encontrada")
                else:
                    for j in pool["jugadores"]:
                        enviar_mensaje(j["numero"], mensaje)
                        if "pareja" in j and j["pareja"]:
                            enviar_mensaje(j["pareja"], mensaje)
                    resp.message(f"✅ Mensaje enviado a la pool {pool['nombre']}")
            except:
                resp.message("❌ Error notificando")
            return str(resp)

    # Comandos de usuario
    if incoming_msg.startswith("lista_pools"):
        msg = ""
        for p in data["pools"]:
            apertura = datetime.fromisoformat(p["apertura_inscripciones"])
            estado = "🟢 Abierta" if datetime.now() >= apertura else f"⏳ Apertura: {apertura.strftime('%Y-%m-%d %H:%M')}"
            msg += f"{p['id']}: {p['nombre']} - Precio: {p['precio']}€ - Horario: {p['horario']} - {estado}\n"
        resp.message(msg if msg else "No hay pools disponibles")
        return str(resp)

    if incoming_msg.startswith("apuntarme_alerta"):
        try:
            _, pool_id = incoming_msg.split(" ")
            pool = next((p for p in data["pools"] if p["id"]==pool_id), None)
            if not pool:
                resp.message("❌ Pool no encontrada")
            else:
                if user not in pool["interesados"]:
                    pool["interesados"].append(user)
                    guardar_datos(data)
                resp.message(f"✅ Te avisaré cuando se abra la inscripción para {pool['nombre']}")
        except:
            resp.message("❌ Error apuntando alerta")
        return str(resp)

    if incoming_msg.startswith("apuntarme"):
        try:
            parts = incoming_msg.split()
            pool_id = parts[1]
            pareja = parts[2] if len(parts) > 2 else None
            pool = next((p for p in data["pools"] if p["id"]==pool_id), None)
            if not pool:
                resp.message("❌ Pool no encontrada")
                return str(resp)
            apertura = datetime.fromisoformat(pool["apertura_inscripciones"])
            if datetime.now() < apertura:
                resp.message(f"⏳ La inscripción para {pool['nombre']} abre el {apertura.strftime('%Y-%m-%d %H:%M')}. Usa 'apuntarme_alerta {pool_id}' para ser avisado.")
                return str(resp)
            pool["jugadores"].append({"numero": user, "pareja": pareja})
            guardar_datos(data)
            if pareja:
                resp.message(f"✅ Te has apuntado con tu pareja ({pareja}) a {pool['nombre']}")
            else:
                resp.message(f"✅ Te has apuntado solo a {pool['nombre']}")
        except:
            resp.message("❌ Error apuntándote")
        return str(resp)

    if incoming_msg.startswith("quitarme"):
        try:
            _, pool_id = incoming_msg.split()
            pool = next((p for p in data["pools"] if p["id"]==pool_id), None)
            if not pool:
                resp.message("❌ Pool no encontrada")
            else:
                pool["jugadores"] = [j for j in pool["jugadores"] if j["numero"] != user]
                guardar_datos(data)
                resp.message(f"✅ Te he quitado de {pool['nombre']}")
        except:
            resp.message("❌ Error quitándote")
        return str(resp)

    if incoming_msg.startswith("mis_pools"):
        msg = ""
        for p in data["pools"]:
            for j in p["jugadores"]:
                if j["numero"] == user:
                    msg += f"{p['id']}: {p['nombre']} - Horario: {p['horario']}\n"
        resp.message(msg if msg else "No estás apuntado a ninguna pool")
        return str(resp)

    if incoming_msg.startswith("ayuda"):
        resp.message(
            "Comandos:\n"
            "- lista_pools\n"
            "- apuntarme <pool> [<pareja>]\n"
            "- apuntarme_alerta <pool>\n"
            "- quitarme <pool>\n"
            "- mis_pools\n"
            "- ayuda\n"
            "Admins: crear_pool, notificar"
        )
        return str(resp)

    resp.message("❌ Comando no reconocido. Escribe 'ayuda'.")
    return str(resp)

@app.route("/", methods=["GET"])
def home():
    return "Bot de WhatsApp profesional activo.", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
