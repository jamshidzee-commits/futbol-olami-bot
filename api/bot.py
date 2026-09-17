import os
import json
import html
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

API_URL = "https://v3.football.api-sports.io/fixtures"

# Нужные турниры
LEAGUE_IDS = {
    39: "🇬🇧 Англия — Premier League",
    140: "🇪🇸 Испания — La Liga",
    135: "🇮🇹 Италия — Serie A",
    78: "🇩🇪 Германия — Bundesliga",
    61: "🇫🇷 Франция — Ligue 1",
    2: "🏆 Champions League",
    3: "🏆 Europa League",
    848: "🏆 Conference League",
}


def get_matches():

    today = datetime.now().strftime("%Y-%m-%d")

    headers = {
        "x-apisports-key": API_KEY,
        "Accept": "application/json"
    }

    params = {
        "date": today,
        "timezone": "Asia/Tashkent"
    }

    response = requests.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=30
    )

    data = response.json()

    # Если API вернул ошибку
    if data.get("errors"):
        return [], "API ERROR: " + str(data["errors"])

    matches = []

    for match in data.get("response", []):

        league = match.get("league", {})
        league_id = league.get("id")
        country = league.get("country", "")

        # Топ-5 + еврокубки
        if league_id in LEAGUE_IDS:
            match["league_name"] = LEAGUE_IDS[league_id]
            matches.append(match)

        # Узбекистан
        elif country == "Uzbekistan":
            match["league_name"] = (
                "🇺🇿 Uzbekistan — " + league.get("name", "Football")
            )
            matches.append(match)

    return matches, None


def send_message(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML"
        },
        timeout=20
    )

    return response.json()


def make_message(matches):

    today = datetime.now().strftime("%d.%m.%Y")

    message = (
        "⚽ <b>FUTBOL OLAMI</b>\n"
        f"📅 <b>Bugungi o‘yinlar — {today}</b>\n"
        "━━━━━━━━━━━━━━\n\n"
    )

    if not matches:
        message += "Bugun tanlangan musobaqalarda o‘yinlar yo‘q. ⚽"
        return message

    current_league = ""

    for match in matches:

        league = match["league_name"]

        if league != current_league:
            message += f"\n<b>{html.escape(league)}</b>\n"
            current_league = league

        home = html.escape(match["teams"]["home"]["name"])
        away = html.escape(match["teams"]["away"]["name"])

        date_time = match["fixture"]["date"]
        time = date_time[11:16]

        status = match["fixture"]["status"]["short"]

        if status in ["FT", "AET", "PEN"]:

            home_score = match["goals"]["home"]
            away_score = match["goals"]["away"]

            message += (
                f"🏁 {time} — "
                f"{home} <b>{home_score}:{away_score}</b> {away}\n"
            )

        elif status in ["1H", "2H", "HT", "ET", "BT", "P"]:

            home_score = match["goals"]["home"] or 0
            away_score = match["goals"]["away"] or 0

            minute = match["fixture"]["status"].get("elapsed")

            message += (
                f"🔴 LIVE {minute or ''}' — "
                f"{home} <b>{home_score}:{away_score}</b> {away}\n"
            )

        else:

            message += (
                f"🕐 {time} — "
                f"{home} ⚔️ {away}\n"
            )

    message += (
        "\n━━━━━━━━━━━━━━\n"
        "📲 <b>Futbol olami</b>\n"
        "⚽ Futbol haqida hammasi!"
    )

    return message


class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        try:

            matches, error = get_matches()

            if error:
                result = send_message(
                    f"⚠️ <b>Futbol olami — API xatosi</b>\n\n"
                    f"<code>{html.escape(error)}</code>"
                )
            else:
                text = make_message(matches)
                result = send_message(text)

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(
                    result,
                    ensure_ascii=False
                ).encode("utf-8")
            )

        except Exception as e:

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(
                str(e).encode("utf-8")
            )
