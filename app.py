from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = "o0a+tl+pfuyNy3UFQ7m+Ep4FX4xnm7+XeH0/4pre23ebgpFCVX9MQdQAlZfX4y9nt5JHgVIJdM+Qu64Wu3hgXzV5sLf0+0avxoGnhW0eaAsdX2uhj4F6kUFpKp9r9RPEj/EcAjf6V6JRI3w4DKYe7wdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "728809e99c8a6e6963802f93beb7d5a1"

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "YOUR_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "YOUR_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/", methods=['GET'])
def home():
    return "NutriFit Bot is running!", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')

    if not signature:
        logging.error("Missing signature header")
        abort(400)

    body = request.get_data(as_text=True)
    logging.info(f"Received LINE webhook request: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logging.error("Invalid signature. Check your LINE credentials.")
        abort(400)

    return 'OK', 200

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    reply_text = f"你想找的食物推薦是: {user_message}!"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
