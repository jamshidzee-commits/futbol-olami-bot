import os
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

API_URL = "https://v3.football.api-sports.io/fixtures"

LEAGUES = {
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
        "x-apisports-key": API_KEY
    }

    all_matches = []

    for league_id, league_name in LEAGUES.items():
        params = {
            "league": league_id,
            "season": 2026,
            "date": today,
            "timezone": "Asia/Tashkent"
        }

        response = requests.get(
            API_URL,
            headers=headers,
            params=params,
            timeout=20
        )

        data = response.json()

        for match in data.get("response", []):
            match["league_name"] = league_name
            all_matches.append(match)

    return all_matches


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data, timeout=20)

    return response.json()


def make_message(matches):
    today = datetime.now().strftime("%d.%m.%Y")

    message = f"⚽ <b>FUTBOL OLAMI</b>\n"
    message += f"📅 <b>Bugungi o‘yinlar — {today}</b>\n\n"

    if not matches:
        message += "Bugun tanlangan ligalarda o‘yinlar yo‘q. ⚽"
        return message

    current_league = ""

    for match in matches:
        league = match["league_name"]

        if league != current_league:
            message += f"\n<b>{league}</b>\n"
            current_league = league

        home = match["teams"]["home"]["name"]
        away = match["teams"]["away"]["name"]

        time = match["fixture"]["date"][11:16]

        status = match["fixture"]["status"]["short"]

        if status in ["FT", "AET", "PEN"]:
            home_score = match["goals"]["home"]
            away_score = match["goals"]["away"]

            score = f"{home_score} : {away_score}"
            message += f"🏁 {time} — {home} <b>{score}</b> {away}\n"

        elif status in ["1H", "2H", "HT", "ET", "P"]:
            home_score = match["goals"]["home"] or 0
            away_score = match["goals"]["away"] or 0

            minute = match["fixture"]["status"].get("elapsed")

            message += (
                f"🔴 <b>LIVE</b> {minute or ''}' "
                f"{home} <b>{home_score}:{away_score}</b> {away}\n"
            )

        else:
            message += f"🕐 {time} — {home} ⚔️ {away}\n"

    message += "\n📲 <b>Futbol olami</b> — futbol haqida hammasi!"

    return message


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            matches = get_matches()
            text = make_message(matches)
            result = send_telegram(text)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(str(result).encode())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
