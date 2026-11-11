import os, json, html, hashlib, re, requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
ADMIN_ID = os.environ["ADMIN_CHAT_ID"]
YT_KEY = os.environ["YOUTUBE_API_KEY"]
TEST = os.environ.get("TEST_MODE", "false") == "true"
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
    s["offered"] = dict(list(s["offered"].items())[-800:])
    s["tries"] = dict(list(s.get("tries", {}).items())[-500:])
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def tg(method, **data):
    r = requests.post(TG + method, json=data, timeout=30)
    print(method, r.status_code, r.text[:150])
    return r.json()

def finished_matches():
    now = datetime.now(TASHKENT)
    out = []
    for code, league in LEAGUES.items():
        for i in (range(7, -1, -1) if TEST else (1, 0)):
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
                out.append({"id": ev["id"], "code": code, "league": league, "end": end,
                            "home": t["home"]["team"]["displayName"], "away": t["away"]["team"]["displayName"],
                            "hg": t["home"].get("score", "0"), "ag": t["away"].get("score", "0")})
    return out

# Официальные каналы: ID каналов YouTube (начинаются с UC...). Заполни сам.
# Как найти: открой канал на YouTube -> «О канале» -> «Поделиться» -> «Копировать ID канала».
# Пример проверенного: UEFA = UCyGa1YEx9ST66rYrJTGIKOw
# Формат: "ID канала": ("Название", [коды лиг, для которых искать на этом канале])
# Коды лиг: eng.1, esp.1, ita.1, ger.1, fra.1, uefa.champions, uefa.europa
OFFICIAL_CHANNELS = {
    "UCyGa1YEx9ST66rYrJTGIKOw": ("UEFA", ["uefa.champions", "uefa.europa"]),
}
MAX_TRIES = 4  # сколько раз искать обзор для одного матча (бережём лимит YouTube)

def short(name):
    stop = {"fc", "cf", "afc", "club", "united", "city", "real", "de"}
    words = [w for w in name.lower().replace("-", " ").split() if w not in stop and len(w) > 2]
    return words[0] if words else name.lower()

def find_video(m):
    """Ищет обзор только на официальных каналах; название должно содержать ОБЕ команды,
    а ролик должен быть опубликован после конца матча."""
    after = m["end"] - timedelta(hours=1)
    for ch_id, (_, codes) in OFFICIAL_CHANNELS.items():
        if m["code"] not in codes:
            continue
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

# ---------- YANGILIKLAR (новости) ----------
# RSS-ленты узбекских сайтов. Если какая-то не работает, в логе будет "NEWS ... 0 ta".
FEEDS = {
    "kun.uz": "https://kun.uz/news/rss",
    "sports.uz": "https://sports.uz/rss",
    "daryo.uz": "https://daryo.uz/feed",
}
# Для общих сайтов (kun.uz, daryo.uz) берём только новости со словами про футбол
FOOTBALL_WORDS = ["futbol", "футбол", "gol", "гол", "superliga", "суперлига", "terma jamoa",
                  "терма жамоа", "murabbiy", "мураббий", "transfer", "трансфер", "paxtakor",
                  "пахтакор", "liga", "лига", "real", "barselona", "барселона", "chempionlar", "чемпионлар"]
NEWS_PER_RUN = 3

def clean(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()

def read_feed(name, url):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 FutbolOlamiBot"})
        root = ET.fromstring(r.content)
    except Exception as e:
        print("NEWS", name, "xato:", e)
        return []
    items = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        desc = clean(it.findtext("description"))
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            dt = None
        if title and link:
            items.append({"source": name, "title": title, "link": link, "desc": desc, "dt": dt})
    print("NEWS", name, len(items), "ta")
    return items

def is_football(n):
    if n["source"] == "sports.uz":
        return True
    text_ = (n["title"] + " " + n["desc"]).lower()
    return any(w in text_ for w in FOOTBALL_WORDS)

def news_text(n):
    desc = n["desc"]
    if len(desc) > 220:
        desc = desc[:220].rsplit(" ", 1)[0] + "…"
    body = f"📰 <b>{html.escape(n['title'])}</b>\n\n"
    if desc:
        body += f"{html.escape(desc)}\n\n"
    body += f"🔗 Manba: <a href=\"{html.escape(n['link'])}\">{n['source']}</a>\n\n<b>FUTBOL OLAMI</b>"
    return body

def offer_news(s):
    seen = s.setdefault("news_seen", [])
    first_run = not s.get("news_init")
    all_news = []
    for name, url in FEEDS.items():
        all_news += [n for n in read_feed(name, url) if is_football(n)]
    now = datetime.now(TASHKENT)
    fresh = []
    for n in all_news:
        key = "n" + hashlib.md5(n["link"].encode()).hexdigest()[:10]
        if key in seen or any(f["key"] == key for f in fresh):
            continue
        if n["dt"] and now - n["dt"] > timedelta(days=7 if TEST else 1):
            continue
        n["key"] = key
        fresh.append(n)
    if first_run and not TEST:
        # Birinchi ishga tushishda eski yangiliklarni yubormaymiz, faqat eslab qolamiz
        seen += [n["key"] for n in fresh]
        s["news_init"] = True
        print("NEWS: birinchi ishga tushish,", len(fresh), "ta yangilik eslab qolindi")
        return
    for n in fresh[:2 if TEST else NEWS_PER_RUN]:
        t = news_text(n)
        tg("sendMessage", chat_id=ADMIN_ID, text=t, parse_mode="HTML",
           reply_markup={"inline_keyboard": [[{"text": "✅ Kanalga", "callback_data": f"pub:{n['key']}"},
                                              {"text": "❌ Kerak emas", "callback_data": f"skip:{n['key']}"}]]})
        s["offered"][n["key"]] = {"text": t}
        seen.append(n["key"])
    s["news_init"] = True
    s["news_seen"] = seen[-2000:]

def offer_new(s):
    now = datetime.now(TASHKENT)
    sent = 0
    for m in finished_matches():
        if TEST and sent >= 2:
            break
        if m["id"] in s["offered"] and not TEST:
            continue
        if now - m["end"] > timedelta(days=8 if TEST else 1.25):
            continue
        if not any(m["code"] in c for _, c in OFFICIAL_CHANNELS.values()):
            continue
        tries = s.setdefault("tries", {})
        if tries.get(m["id"], 0) >= MAX_TRIES and not TEST:
            continue
        tries[m["id"]] = tries.get(m["id"], 0) + 1
        url = find_video(m)
        if not url:
            continue
        t = text(m, url)
        tg("sendMessage", chat_id=ADMIN_ID, text=t, parse_mode="HTML",
           reply_markup={"inline_keyboard": [[{"text": "✅ Kanalga", "callback_data": f"pub:{m['id']}"},
                                              {"text": "❌ Kerak emas", "callback_data": f"skip:{m['id']}"}]]})
        s["offered"][m["id"]] = {"text": t}
        sent += 1

if __name__ == "__main__":
    s = load()
    handle_buttons(s)
    offer_new(s)
    offer_news(s)
    save(s)
