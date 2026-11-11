import os, json, html, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
ADMIN_ID = os.environ["ADMIN_CHAT_ID"]
YT_KEY = os.environ["YOUTUBE_API_KEY"]
TG = f"https://api.telegram.org/bot{BOT}/"
TASHKENT = ZoneInfo("Asia/Tashkent")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"
STATE = "highlights.json"
LEAGUES = {"eng.1": "Premier Liga", "esp.1": "La Liga", "ita.1": "Seriya A",
           "ger.1": "Bundesliga", "fra.1": "Ligue 1", "uefa.champions": "Chempionlar Ligasi",
           "uefa.europa": "Yevropa Ligasi"}

def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"offered": {}, "offset": 0}

def save(s):
    s["offered"] = dict(list(s["offered"].items())[-500:])
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def tg(method, **data):
    r = requests.post(TG + method, json=data, timeout=30)
    print(method, r.status_code, r.text[:150])
    return r.json()

def finished_matches():
    now = datetime.now(TASHKENT)
    out = []
    for code, league in LEAGUES.items():
        for i in (1, 0):
            d = (now - timedelta(days=i)).strftime("%Y%m%d")
            try:
                evs = requests.get(ESPN.format(code=code), params={"dates": d}, timeout=30).json().get("events", [])
            except Exception as e:
                print("ESPN", e); continue
            for ev in evs:
                c = ev["competitions"][0]
                if not c["status"]["type"].get("completed"):
                    continue
                t = {x["homeAway"]: x for x in c["competitors"]}
                end = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")) + timedelta(hours=2)
                out.append({"id": ev["id"], "league": league, "end": end,
                            "home": t["home"]["team"]["displayName"], "away": t["away"]["team"]["displayName"],
                            "hg": t["home"].get("score", "0"), "ag": t["away"].get("score", "0")})
    return out

# Официальные каналы: ID каналов YouTube (начинаются с UC...). Заполни сам.
# Как найти: открой канал на YouTube -> «О канале» -> «Поделиться» -> «Копировать ID канала».
# Пример проверенного: UEFA = UCyGa1YEx9ST66rYrJTGIKOw
OFFICIAL_CHANNELS = {
    "UCyGa1YEx9ST66rYrJTGIKOw": "UEFA",
}

def short(name):
    stop = {"fc", "cf", "afc", "club", "united", "city", "real", "de"}
    words = [w for w in name.lower().replace("-", " ").split() if w not in stop and len(w) > 2]
    return words[0] if words else name.lower()

def find_video(m):
    """Ищет обзор только на официальных каналах; название должно содержать ОБЕ команды,
    а ролик должен быть опубликован после конца матча."""
    after = m["end"] - timedelta(hours=1)
    for ch_id in OFFICIAL_CHANNELS:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "key": YT_KEY, "part": "snippet", "type": "video", "maxResults": 10,
            "channelId": ch_id, "order": "date",
            "q": f"{m['home']} {m['away']}",
            "publishedAfter": after.strftime("%Y-%m-%dT%H:%M:%SZ")}, timeout=30).json()
        for it in r.get("items", []):
            title = it["snippet"]["title"].lower()
            if short(m["home"]) in title and short(m["away"]) in title:
                return f"https://www.youtube.com/watch?v={it['id']['videoId']}"
    return None

def text(m, url):
    return (f"⚽ <b>{html.escape(m['home'])} {m['hg']}:{m['ag']} {html.escape(m['away'])}</b>\n"
            f"🏆 {m['league']}\n\n🎬 O'yin sharhi: {url}\n\n<b>FUTBOL OLAMI</b>")

def handle_buttons(s):
    ups = tg("getUpdates", offset=s["offset"], timeout=0, allowed_updates=["callback_query"]).get("result", [])
    for u in ups:
        s["offset"] = u["update_id"] + 1
        q = u.get("callback_query")
        if not q or str(q["from"]["id"]) != str(ADMIN_ID):
            continue
        action, mid = q["data"].split(":", 1)
        item = s["offered"].get(mid)
        if action == "pub" and item and not item.get("done"):
            tg("sendMessage", chat_id=CHANNEL_ID, text=item["text"], parse_mode="HTML")
            item["done"] = "published"
            note = "✅ Kanalga joylandi"
        else:
            if item: item["done"] = "skipped"
            note = "❌ O'tkazib yuborildi"
        tg("answerCallbackQuery", callback_query_id=q["id"], text=note)
        tg("editMessageReplyMarkup", chat_id=q["message"]["chat"]["id"],
           message_id=q["message"]["message_id"], reply_markup={"inline_keyboard": []})

def offer_new(s):
    now = datetime.now(TASHKENT)
    for m in finished_matches():
        if m["id"] in s["offered"] or now - m["end"] > timedelta(hours=30):
            continue
        url = find_video(m)
        if not url:
            continue
        t = text(m, url)
        tg("sendMessage", chat_id=ADMIN_ID, text=t, parse_mode="HTML",
           reply_markup={"inline_keyboard": [[{"text": "✅ Kanalga", "callback_data": f"pub:{m['id']}"},
                                              {"text": "❌ Kerak emas", "callback_data": f"skip:{m['id']}"}]]})
        s["offered"][m["id"]] = {"text": t}

if __name__ == "__main__":
    s = load()
    handle_buttons(s)
    offer_new(s)
    save(s)
