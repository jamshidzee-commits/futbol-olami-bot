import os
import json
import html
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io/fixtures"

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

    if data.get("errors"):
        return [], str(data["errors"])

    matches = []

    for match in data.get("response", []):

        league = match.get("league", {})
        league_id = league.get("id")
        country = league.get("country", "")

        if league_id in LEAGUE_IDS:

            match["league_name"] = LEAGUE_IDS[league_id]
            matches.append(match)

        elif country == "Uzbekistan":

            match["league_name"] = (
                "🇺🇿 Uzbekistan — "
                + league.get("name", "Football")
            )

            matches.append(match)

    # Сортировка по времени
    matches.sort(
        key=lambda x: x["fixture"]["date"]
    )

    return matches, None


def make_message(matches):

    today = datetime.now().strftime("%d.%m.%Y")

    message = (
        "⚽ <b>FUTBOL OLAMI</b>\n"
        f"📅 <b>Bugungi o‘yinlar — {today}</b>\n"
        "━━━━━━━━━━━━━━\n\n"
    )

    if not matches:

        message += (
            "Bugun tanlangan musobaqalarda "
            "o‘yinlar yo‘q. ⚽"
        )

        return message

    current_league = ""

    for match in matches:

        league = match["league_name"]

        if league != current_league:

            message += (
                f"\n<b>{html.escape(league)}</b>\n"
            )

            current_league = league

        home = html.escape(
            match["teams"]["home"]["name"]
        )

        away = html.escape(
            match["teams"]["away"]["name"]
        )

        time = match["fixture"]["date"][11:16]

        status = match["fixture"]["status"]["short"]

        if status in ["FT", "AET", "PEN"]:

            home_score = match["goals"]["home"]
            away_score = match["goals"]["away"]

            message += (
                f"🏁 {time} — "
                f"{home} <b>{home_score}:{away_score}</b> "
                f"{away}\n"
            )

        elif status in [
            "1H", "2H", "HT", "ET", "BT", "P"
        ]:

            home_score = match["goals"]["home"] or 0
            away_score = match["goals"]["away"] or 0

            minute = (
                match["fixture"]["status"]
                .get("elapsed")
            )

            message += (
                f"🔴 <b>LIVE {minute or ''}'</b> — "
                f"{home} <b>{home_score}:{away_score}</b> "
                f"{away}\n"
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


def send_message(text):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

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


class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        authorization = self.headers.get(
            "authorization", ""
        )

        if authorization != f"Bearer {CRON_SECRET}":

            self.send_response(401)
            self.end_headers()
            self.wfile.write(
                b"Unauthorized"
            )
            return

        try:

            matches, error = get_matches()

            if error:

                result = send_message(
                    "⚠️ <b>Futbol olami</b>\n\n"
                    "API xatosi:\n"
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
            self.end_headers()

            self.wfile.write(
                str(e).encode("utf-8")
            )
