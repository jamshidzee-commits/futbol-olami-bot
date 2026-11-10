import os
import json
import html
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_KEY = os.environ["FOOTBALL_API_KEY"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
TEST_MODE = os.environ.get("TEST_MODE", "false") == "true"

TASHKENT = ZoneInfo("Asia/Tashkent")
API_URL = "https://v3.football.api-sports.io/fixtures"
SENT_FILE = "sent.json"

LEAGUES = {
    39: "🇬🇧 Premier League",
    140: "🇪🇸 La Liga",
    135: "🇮🇹 Serie A",
    78: "🇩🇪 Bundesliga",
    61: "🇫🇷 Ligue 1",
    2: "🏆 Champions League",
    3: "🏆 Europa League",
    848: "🏆 Conference League",
}

FINISHED = {"FT", "AET", "PEN"}


def load_sent():
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent)[-2000:], f)


def get_fixtures(date_string):
    r = requests.get(
        API_URL,
        headers={"x-apisports-key": API_KEY},
        params={"date": date_string, "timezone": "Asia/Tashkent"},
        timeout=30,
    )
    data = r.json()
    if data.get("errors"):
        print("API ERROR:", data["errors"])
        return []
    return data.get("response", [])


def league_label(m):
    league = m["league"]
    if league["id"] in LEAGUES:
        return LEAGUES[league["id"]]
    if league.get("country") == "Uzbekistan":
        return "🇺🇿 " + league.get("name", "Uzbekistan")
    return None


def make_text(m, label):
    home = html.escape(m["teams"]["home"]["name"])
    away = html.escape(m["teams"]["away"]["name"])
    hg = m["goals"]["home"]
    ag = m["goals"]["away"]
    status = m["fixture"]["status"]["short"]

    if hg > ag:
        home_line = f"✅ <b>{home}</b>"
        away_line = f"▫️ {away}"
    elif ag > hg:
        home_line = f"▫️ {home}"
        away_line = f"✅ <b>{away}</b>"
    else:
        home_line = f"🤝 {home}"
        away_line = f"🤝 {away}"

    extra = ""
    if status == "AET":
        extra = "\n⏱ Qo‘shimcha vaqtdan so‘ng"
    elif status == "PEN":
        pen = m.get("score", {}).get("penalty", {})
        extra = f"\n🥅 Penaltilar: {pen.get('home')}:{pen.get('away')}"

    return (
        "⚽ <b>FUTBOL OLAMI</b>\n"
        f"{html.escape(label)}\n"
        "━━━━━━━━━━━━━━\n\n"
        f"{home_line}\n"
        f"{away_line}\n\n"
        f"🏁 <b>Hisob: {hg}:{ag}</b>{extra}\n\n"
        "━━━━━━━━━━━━━━\n"
        "📲 <b>Futbol olami</b> — futbol haqida hammasi!"
    )


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    print("TELEGRAM:", r.status_code, r.text[:200])
    return r.ok


def main():
    now = datetime.now(TASHKENT)
    dates = [
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d"),
    ]

    finished = []
    for d in dates:
        for m in get_fixtures(d):
            if m["fixture"]["status"]["short"] not in FINISHED:
                continue
            label = league_label(m)
            if label:
                finished.append((m, label))

    finished.sort(key=lambda x: x[0]["fixture"]["timestamp"])
    sent = load_sent()

    if TEST_MODE:
        print("TEST MODE: sending last 3 finished matches")
        for m, label in finished[-3:]:
            send(make_text(m, label))
        return

    for m, label in finished:
        fid = str(m["fixture"]["id"])
        if fid in sent:
            continue
        if send(make_text(m, label)):
            sent.add(fid)

    save_sent(sent)


main()
