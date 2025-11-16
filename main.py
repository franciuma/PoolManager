from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
from datetime import datetime
import threading
import time
import os

# Configuración
DATA_FILE = "pools.json"
app = Flask(__name__)

# Número(s) de admin fijo(s)
ADMINS = os.environ.get("ADMINS", "").split(",")

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

# Calcular plazas disponibles
def plazas_disponibles(pool):
    max_jugadores = pool["max_pistas"] * 4
    jugadores_actuales = sum([2 if j.get("pareja") else 1 for j in pool["jugadores"]])
    return max_jugadores - jugadores_actuales

# Función para enviar notificaciones de apertura de inscripciones
def notificar_apertura():
    while True:
        now = datetime.now()
        for pool in data["pools"]:
            apertura = datetime.fromisoformat(pool["apertura_inscripciones"])
            if "notificado" not in pool and now >= apertura:
                for user in pool["interesados"]:
                    enviar_mensaje(user, f"📢 La inscripción para {pool['nombre']} ya está abierta. Responde con el número de la pool para apuntarte.")
                pool["notificado"] = True
                pool["interesados"] = []  # limpiar interesados
                guardar_datos(data)
        time.sleep(60)

# Función simulada de envío (Twilio envía desde webhook)
def enviar_mensaje(to, mensaje):
    # Aquí podrías usar la API de Twilio para enviar mensaje proactivo si tu plan lo permite
    print(f"Enviar a {to}: {mensaje}")

# Iniciar scheduler en segundo plano
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

    # Bienvenida a usuarios nuevos
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
                _, nombre, precio, horario, apertura, max_pistas = incoming_msg.split(" ", 5)
                pool_id = nombre.lower().replace(" ", "_")
                data["pools"].append({
                    "id": pool_id,
                    "nombre": nombre,
                    "precio": float(precio),
                    "horario": horario,
                    "apertura_inscripciones": apertura,
                    "max_pistas": int(max_pistas),
                    "jugadores": [],
                    "interesados": []
                })
                guardar_datos(data)
                resp.message(f"✅ Pool '{nombre}' creada con ID {pool_id}")
            except:
                resp.message("❌ Error creando pool. Usa: crear_pool <nombre> <precio> <horario> <apertura_iso> <max_pistas>")
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
        if not data["pools"]:
            resp.message("No hay pools disponibles.")
            return str(resp)
        msg = ""
        for i, p in enumerate(data["pools"], start=1):
            apertura = datetime.fromisoformat(p["apertura_inscripciones"])
            estado = "🟢 Abierta" if datetime.now() >= apertura else f"⏳ Apertura: {apertura.strftime('%Y-%m-%d %H:%M')}"
            disponibles = plazas_disponibles(p)
            msg += f"{i}️⃣ {p['nombre']} - Precio: {p['precio']}€ - Horario: {p['horario']} - {estado} - Plazas disponibles: {disponibles}\n"
        msg += "\nResponde con el número de la pool para apuntarte."
        resp.message(msg)
        return str(resp)

    # Selección por número de pool
    if incoming_msg.isdigit():
        idx = int(incoming_msg) - 1
        if idx < 0 or idx >= len(data["pools"]):
            resp.message("❌ Número de pool inválido. Escribe 'lista_pools' para ver las disponibles.")
            return str(resp)
        pool = data["pools"][idx]
        if datetime.now() < datetime.fromisoformat(pool["apertura_inscripciones"]):
            resp.message(f"⏳ La inscripción para {pool['nombre']} abre el {datetime.fromisoformat(pool['apertura_inscripciones']).strftime('%Y-%m-%d %H:%M')}.")
            return str(resp)
        if plazas_disponibles(pool) <= 0:
            resp.message(f"❌ Lo sentimos, no quedan plazas disponibles en {pool['nombre']}.")
            return str(resp)

        # Guardar temporalmente la pool elegida en memoria del usuario
        # Para simplificar aquí pedimos el siguiente mensaje con 'solo' o teléfono de pareja + lado
        resp.message(
            f"Has seleccionado {pool['nombre']}.\n"
            "Responde 'solo <lado>' o '<tel_pareja> <lado>'\n"
            "Lado: derecha, revés, da igual"
        )
        # Guardamos temporalmente la selección
        if "seleccion_temp" not in data:
            data["seleccion_temp"] = {}
        data["seleccion_temp"][user] = idx
        guardar_datos(data)
        return str(resp)

    # Procesar apuntarse con datos
    if user in data.get("seleccion_temp", {}):
        parts = incoming_msg.split()
        if len(parts) < 2:
            resp.message("❌ Formato incorrecto. Responde 'solo <lado>' o '<tel_pareja> <lado>'.")
            return str(resp)
        pareja = None
        lado = parts[-1]
        if parts[0] != "solo":
            pareja = parts[0]
        idx = data["seleccion_temp"].pop(user)
        pool = data["pools"][idx]
        pool["jugadores"].append({"numero": user, "pareja": pareja, "lado": lado})
        guardar_datos(data)
        msg = f"✅ Te has apuntado a {pool['nombre']}"
        if pareja:
            msg += f" con tu pareja ({pareja})"
        msg += f" - Lado: {lado}"
        resp.message(msg)
        return str(resp)

    # Comandos de usuario simples
    if incoming_msg.startswith("mis_pools"):
        msg = ""
        for p in data["pools"]:
            for j in p["jugadores"]:
                if j["numero"] == user:
                    msg += f"{p['nombre']} - Horario: {p['horario']} - Lado: {j.get('lado', 'da igual')}\n"
        resp.message(msg if msg else "No estás apuntado a ninguna pool")
        return str(resp)

    if incoming_msg.startswith("ayuda"):
        resp.message(
            "Comandos:\n"
            "- lista_pools\n"
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
