from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

players = set()  # lista en memoria para la prueba de concepto


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    user = request.values.get("From", "")

    resp = MessagingResponse()

    if "apuntarme" in incoming_msg:
        players.add(user)
        resp.message("✅ Te he apuntado a la lista.")
    elif "quitarme" in incoming_msg:
        players.discard(user)
        resp.message("❎ Te he quitado de la lista.")
    elif "lista" in incoming_msg:
        if players:
            txt = "📋 Lista actual:\n" + "\n".join(players)
            resp.message(txt)
        else:
            resp.message("📋 La lista está vacía.")
    else:
        resp.message("🤖 Comandos disponibles:\n- apuntarme\n- quitarme\n- lista")

    return str(resp)


@app.route("/", methods=["GET"])
def home():
    return "Bot de WhatsApp activo.", 200
