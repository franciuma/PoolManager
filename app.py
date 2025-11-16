from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# Lista en memoria (una sola lista global para la prueba)
lista_jugadores = set()

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "").strip().lower()
    numero = request.form.get("From", "")  # Ej: whatsapp:+34600111222

    resp = MessagingResponse()
    reply = resp.message()

    nombre_usuario = numero.replace("whatsapp:", "")

    if mensaje == "apuntarme":
        lista_jugadores.add(nombre_usuario)
        reply.body(f"Te he apuntado, {nombre_usuario} ✔️")
    
    elif mensaje == "quitarme":
        if nombre_usuario in lista_jugadores:
            lista_jugadores.remove(nombre_usuario)
            reply.body(f"Te he quitado de la lista, {nombre_usuario} ❌")
        else:
            reply.body("No estabas apuntado 👀")
    
    elif mensaje == "lista":
        if len(lista_jugadores) == 0:
            reply.body("La lista está vacía 🟦")
        else:
            jugadores = "\n".join(lista_jugadores)
            reply.body(f"Jugadores apuntados:\n{jugadores}")
    
    elif mensaje == "ayuda":
        reply.body(
            "Comandos disponibles:\n"
            "- apuntarme\n"
            "- quitarme\n"
            "- lista\n"
            "- ayuda"
        )
    else:
        reply.body("No reconozco ese comando. Escribe 'ayuda'.")

    return str(resp)

@app.route("/")
def home():
    return "Bot de pádel funcionando en Render ✔️"
