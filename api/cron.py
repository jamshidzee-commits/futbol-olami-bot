import os
import json
import html
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io"

TASHKENT = ZoneInfo("Asia/Tashkent")

# Основные турниры
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

# Лиги, для которых публикуем таблицы
STANDINGS_LEAGUES = [
    39,
    140,
    135,
    78,
    61,
    2,
    3,
    848,
]


def api_get(endpoint, params):
    headers = {
        "x-apisports-key": API_KEY,
        "Accept": "application/json",
    }

    response = requests.get(
        f"{API_URL}/{endpoint}",
        headers=headers,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise Exception(str(data["errors"]))

    return data.get("response", [])


def get_fixtures(date_string):
    return api_get(
        "fixtures",
        {
            "date": date_string,
            "timezone": "Asia/Tashkent",
        },
    )


def get_selected_fixtures(date_string):
    fixtures = get_fixtures(date_string)

    result = []

    for match in fixtures:
        league = match.get("league", {})
        league_id = league.get("id")
        country = league.get("country", "")

        if league_id in LEAGUE_IDS:
            match["league_name"] = LEAGUE_IDS[league_id]
            result.append(match)

        elif country == "Uzbekistan":
            match["league_name"] = (
                "🇺🇿 Uzbekistan — "
                + league.get("name", "Football")
            )
            result.append(match)

    result.sort(
        key=lambda x: (
            x.get("league_name", ""),
            x.get("fixture", {}).get("date", ""),
        )
    )

    return result


def format_fixture(match):
    home = html.escape(
        match.get("teams", {}).get("home", {}).get("name", "?")
    )

    away = html.escape(
        match.get("teams", {}).get("away", {}).get("name", "?")
    )

    fixture = match.get("fixture", {})
    status_data = fixture.get("status", {})
    status = status_data.get("short", "")

    match_date = fixture.get("date", "")
    time = match_date[11:16] if len(match_date) >= 16 else "--:--"

    goals = match.get("goals", {})

    home_score = goals.get("home")
    away_score = goals.get("away")

    # Завершённый матч
    if status in ["FT", "AET", "P"]:
        if home_score is None:
            home_score = 0

        if away_score is None:
            away_score = 0

        return (
            f"🏁 {time} — {home} "
            f"<b>{home_score}:{away_score}</b> {away}"
        )

    # LIVE
    if status in [
        "1H",
        "2H",
        "HT",
        "ET",
        "BT",
        "P",
    ]:
        home_score = home_score or 0
        away_score = away_score or 0

        minute = status_data.get("elapsed")

        minute_text = ""
        if minute:
            minute_text = f" {minute}'"

        return (
            f"🔴 <b>LIVE{minute_text}</b> — "
            f"{home} <b>{home_score}:{away_score}</b> {away}"
        )

    # Предстоящий матч
    return f"🕐 {time} — {home} ⚔️ {away}"


def build_fixture_message(title, date_string, matches):
    date_object = datetime.strptime(date_string, "%Y-%m-%d")

    display_date = date_object.strftime("%d.%m.%Y")

    message = (
        f"⚽ <b>FUTBOL OLAMI</b>\n"
        f"{title}\n"
        f"📅 {display_date}\n"
        f"━━━━━━━━━━━━━━\n"
    )

    if not matches:
        message += "\n⚽ Матчей в выбранных турнирах нет."
        return message

    current_league = None

    for match in matches:
        league = match.get(
            "league_name",
            "Football",
        )

        if league != current_league:
            message += f"\n<b>{html.escape(league)}</b>\n"
            current_league = league

        message += format_fixture(match) + "\n"

    message += (
        "\n━━━━━━━━━━━━━━\n"
        "📲 <b>Futbol olami</b>\n"
        "⚽ Futbol haqida hammasi!"
    )

    return message


def get_standings(league_id, season):
    return api_get(
        "standings",
        {
            "league": league_id,
            "season": season,
        },
    )


def build_standings_message(league_id, league_name, season):
    data = get_standings(league_id, season)

    if not data:
        return None

    league_data = data[0].get("league", {})
    standings = league_data.get("standings", [])

    if not standings:
        return None

    # Иногда API возвращает несколько групп
    teams = []

    for group in standings:
        for item in group:
            teams.append(item)

    if not teams:
        return None

    message = (
        f"📊 <b>{html.escape(league_name)}</b>\n"
        f"🏆 Таблица сезона {season}\n"
        "━━━━━━━━━━━━━━\n"
    )

    for item in teams:
        rank = item.get("rank", "")
        team = item.get("team", {})
        team_name = html.escape(team.get("name", "?"))

        points = item.get("points", 0)
        played = item.get("all", {}).get("played", 0)
        wins = item.get("all", {}).get("win", 0)
        draws = item.get("all", {}).get("draw", 0)
        losses = item.get("all", {}).get("lose", 0)

        message += (
            f"<b>{rank}.</b> {team_name}\n"
            f"   🎮 {played}  "
            f"✅ {wins}  "
            f"🤝 {draws}  "
            f"❌ {losses}  "
            f"🏆 <b>{points}</b>\n"
        )

    message += (
        "\n━━━━━━━━━━━━━━\n"
        "📲 <b>Futbol olami</b>"
    )

    return message


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    result = response.json()

    if not result.get("ok"):
        raise Exception(str(result))

    return result


def send_long_message(text):
    # Telegram имеет ограничение примерно 4096 символов.
    max_length = 3900

    if len(text) <= max_length:
        send_message(text)
        return

    parts = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                parts.append(current)

            current = line
        else:
            if current:
                current += "\n"

            current += line

    if current:
        parts.append(current)

    for part in parts:
        send_message(part)


def get_dates():
    now = datetime.now(TASHKENT)

    today = now.date()
    yesterday = today - timedelta(days=1)

    return (
        yesterday.strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    )


def run_bot():
    yesterday, today = get_dates()

    # ==============================
    # 1. РЕЗУЛЬТАТЫ ВЧЕРА
    # ==============================

    yesterday_matches = get_selected_fixtures(yesterday)

    yesterday_message = build_fixture_message(
        "🏁 <b>Результаты вчерашних матчей</b>",
        yesterday,
        yesterday_matches,
    )

    send_long_message(yesterday_message)

    # ==============================
    # 2. МАТЧИ СЕГОДНЯ
    # ==============================

    today_matches = get_selected_fixtures(today)

    today_message = build_fixture_message(
        "📅 <b>Матчи сегодня</b>",
        today,
        today_matches,
    )

    send_long_message(today_message)

    # ==============================
    # 3. ТАБЛИЦЫ
    # ==============================

    now = datetime.now(TASHKENT)

    # Футбольный сезон обычно начинается
    # летом. После июля используем текущий год.
    if now.month >= 7:
        season = now.year
    else:
        season = now.year - 1

    for league_id in STANDINGS_LEAGUES:
        league_name = LEAGUE_IDS[league_id]

        try:
            standings_message = build_standings_message(
                league_id,
                league_name,
                season,
            )

            if standings_message:
                send_long_message(standings_message)

        except Exception as e:
            print(
                f"Standings error "
                f"{league_id}: {e}"
            )


class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        authorization = self.headers.get(
            "authorization",
            ""
        )

        expected = f"Bearer {CRON_SECRET}"

        if not CRON_SECRET or authorization != expected:
            self.send_response(401)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.end_headers()
            self.wfile.write(
                b"Unauthorized"
            )
            return

        try:
            run_bot()

            result = {
                "ok": True,
                "message": "Futbol olami cron completed",
            }

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

            print(f"CRON ERROR: {e}")

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(e),
                    },
                    ensure_ascii=False
                ).encode("utf-8")
            )
