import os
import json
import html
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
TEST_MODE = os.environ.get("TEST_MODE", "false") == "true"

TASHKENT = ZoneInfo("Asia/Tashkent")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"
SENT_FILE = "sent.json"

# Код лиги в ESPN -> красивое название
LEAGUES = {
    "eng.1": "🇬🇧 Premier League",
    "esp.1": "🇪🇸 La Liga",
    "ita.1": "🇮🇹 Serie A",
    "ger.1": "🇩🇪 Bundesliga",
    "fra.1": "🇫🇷 Ligue 1",
    "uefa.champions": "🏆 Champions League",
    "uefa.europa": "🏆 Europa League",
    "uefa.europa.conf": "🏆 Conference League",
}


def load_sent():
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent)[-3000:], f)


def get_events(code, date_string):
    try:
        r = requests.get(
            ESPN.format(code=code),
            params={"dates": date_string.replace("-", ""), "limit": 100},
            timeout=30,
        )
        r.raise_for_status()
        events = r.json().get("events", [])
        print("ESPN", code, date_string, "events:", len(events))
        return events
    except Exception as e:
        print("ESPN ERROR", code, date_string, e)
        return []


def parse_event(ev):
    comp = ev["competitions"][0]
    status = comp["status"]["type"]
    if not status.get("completed"):
        return None
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    return {
        "id": ev["id"],
        "date": ev.get("date", ""),
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "hg": int(float(home.get("score", 0) or 0)),
        "ag": int(float(away.get("score", 0) or 0)),
        "shootout": status.get("name") == "STATUS_FINAL_PEN",
        "aet": status.get("name") == "STATUS_FINAL_AET",
    }


def make_text(m, label):
    home = html.escape(m["home"])
    away = html.escape(m["away"])
    hg, ag = m["hg"], m["ag"]

    if hg > ag:
        home_line, away_line = f"✅ <b>{home}</b>", f"▫️ {away}"
    elif ag > hg:
        home_line, away_line = f"▫️ {home}", f"✅ <b>{away}</b>"
    else:
        home_line, away_line = f"🤝 {home}", f"🤝 {away}"

    extra = ""
    if m["aet"]:
        extra = "\n⏱ Qo‘shimcha vaqtdan so‘ng"
    elif m["shootout"]:
        extra = "\n🥅 Penaltilar seriyasida"

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
    # Тест: смотрим 7 дней назад, обычный запуск: вчера и сегодня
    days_back = 7 if TEST_MODE else 1
    dates = [
        (now - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days_back, -1, -1)
    ]

    finished = []
    for code, label in LEAGUES.items():
        for d in dates:
            for ev in get_events(code, d):
                m = parse_event(ev)
                if m:
                    finished.append((m, label))

    finished.sort(key=lambda x: x[0]["date"])
    print("FINISHED FOUND:", len(finished))
    sent = load_sent()

    if TEST_MODE:
        print("TEST MODE: sending last 3 finished matches")
        for m, label in finished[-3:]:
            send(make_text(m, label))
        return

    for m, label in finished:
        key = f"espn-{m['id']}"
        if key in sent:
            continue
        if send(make_text(m, label)):
            sent.add(key)

    save_sent(sent)


main()
