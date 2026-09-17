import os
import json
import requests
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        data = {
            "chat_id": CHANNEL_ID,
            "text": "⚽ <b>Futbol olami</b>\n\n🤖 Бот успешно подключен!\n🇺🇿 Tez orada futbol yangiliklari avtomatik chiqadi.",
            "parse_mode": "HTML"
        }

        response = requests.post(
            url,
            json=data,
            timeout=20
        )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        self.wfile.write(
            json.dumps(response.json()).encode()
        )
