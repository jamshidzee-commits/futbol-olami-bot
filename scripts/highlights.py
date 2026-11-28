import os, json, html, hashlib, re, time, unicodedata, requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
ADMIN_ID = os.environ["ADMIN_CHAT_ID"]
YT_KEY = os.environ["YOUTUBE_API_KEY"]
TEST = os.environ.get("TEST_MODE", "false") == "true"
GROUP_ID = os.environ.get("GROUP_ID", "").strip()  # masalan @uzb_fut_fan_club
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
    s["videos"] = dict(list(s.get("videos", {}).items())[-800:])
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def tg(method, **data):
    try:
        r = requests.post(TG + method, json=data, timeout=30)
        print(method, r.status_code, r.text[:150])
        return r.json()
    except Exception as e:  # сеть / не-JSON ответ не должны ронять весь запуск
        print("TG ERROR", method, e)
        return {"ok": False, "result": []}

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
MAX_TRIES = 50  # обзор ищем до 24 часов после матча (поиск каждые 30 мин, дешёвый)

# Rasmiy liga kanallari: ID ni bot o'zi handle bo'yicha topadi va kanal nomini tekshiradi
# (nomi mos kelmasa — o'tkazib yuboradi, noto'g'ri kanaldan video olmaydi).
# Формат: код лиги: (слово, которое должно быть в названии канала, [варианты @handle])
LEAGUE_HANDLES = {
    "eng.1": ("premier league", ["premierleague"]),
    "esp.1": ("laliga", ["LaLiga"]),
    "ita.1": ("serie a", ["SerieA"]),
    "ger.1": ("bundesliga", ["bundesliga"]),
    "fra.1": ("ligue 1", ["ligue1ubereats", "Ligue1McDonalds", "Ligue1"]),
}
# Adminga tugmali taklif (eski xatti-harakat) faqat shu ligalar uchun; qolganlarda faqat havola eslab qolinadi
DM_CODES = {c for _, cs in OFFICIAL_CHANNELS.values() for c in cs}

def short(name):
    stop = {"fc", "cf", "afc", "club", "united", "city", "real", "de"}
    words = [w for w in name.lower().replace("-", " ").split() if w not in stop and len(w) > 2]
    return words[0] if words else name.lower()

def norm(t):
    return "".join(c for c in unicodedata.normalize("NFKD", (t or "").lower()) if not unicodedata.combining(c))

ALIASES = {
    "manchester city": ["man city", "manchester city"], "manchester united": ["man utd", "man united", "manchester united"],
    "tottenham hotspur": ["tottenham", "spurs"], "newcastle united": ["newcastle"], "west ham united": ["west ham"],
    "wolverhampton wanderers": ["wolves", "wolverhampton"], "nottingham forest": ["nottingham forest", "nott'm forest", "forest"],
    "brighton & hove albion": ["brighton"], "leeds united": ["leeds"], "leicester city": ["leicester"],
    "real madrid": ["real madrid"], "atletico madrid": ["atletico"], "athletic club": ["athletic"],
    "ac milan": ["milan"], "inter milan": ["inter"], "as roma": ["roma"],
    "paris saint-germain": ["psg", "paris saint", "paris sg"], "as monaco": ["monaco"],
    "olympique marseille": ["marseille"], "olympique lyonnais": ["lyon"],
    "bayern munich": ["bayern"], "borussia dortmund": ["dortmund"], "bayer leverkusen": ["leverkusen"],
    "borussia monchengladbach": ["gladbach", "monchengladbach"], "eintracht frankfurt": ["frankfurt"], "rb leipzig": ["leipzig"],
}
SKIP_WORDS = ("preview", "press conference", "reaction", "interview", "team news", "predict", "training", "trailer")

def team_keys(name):
    n = norm(name)
    return ALIASES.get(n) or [n, norm(short(name))]

_uploads = {}

def uploads(ch_id, pages=1):
    """Последние видео канала: 50 на страницу (1 единица квоты за страницу, вместо дорогого поиска за 100)."""
    key = (ch_id, pages)
    if key not in _uploads:
        out, token = [], None
        try:
            for _ in range(pages):
                params = {"key": YT_KEY, "part": "snippet", "playlistId": "UU" + ch_id[2:], "maxResults": 50}
                if token:
                    params["pageToken"] = token
                r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params, timeout=30).json()
                out += [(it["snippet"]["title"], it["snippet"]["publishedAt"], it["snippet"]["resourceId"]["videoId"])
                        for it in r.get("items", [])]
                token = r.get("nextPageToken")
                if not token:
                    break
            print("YT UPLOADS", ch_id, len(out))
        except Exception as e:
            print("YOUTUBE ERROR", ch_id, e)
        _uploads[key] = out
    return _uploads[key]

def resolve_channels(s):
    resolve_qsport(s)
    resolve_setanta(s)
    found = s.setdefault("channels", {})
    for code, (need, handles) in LEAGUE_HANDLES.items():
        for h in handles:
            if code in found:
                break
            try:
                r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                                 params={"key": YT_KEY, "part": "snippet", "forHandle": "@" + h}, timeout=30).json()
            except Exception as e:
                print("YT CHANNEL ERROR", h, e)
                continue
            for it in r.get("items", []):
                print("YT CHANNEL", h, "->", it["id"], it["snippet"]["title"])
                if need in it["snippet"]["title"].lower():
                    found[code] = it["id"]
                    break

def resolve_qsport(s):
    """Qsport Uzbekistan (@QsportUzbekistan): rus tilida «Обзор матча» roliklari — barcha ligalar uchun qo'shimcha manba."""
    found = s.setdefault("channels", {})
    if "qsport" in found:
        return
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                         params={"key": YT_KEY, "part": "snippet", "forHandle": "@QsportUzbekistan"}, timeout=30).json()
    except Exception as e:
        print("YT CHANNEL ERROR qsport", e)
        return
    for it in r.get("items", []):
        print("YT CHANNEL qsport ->", it["id"], it["snippet"]["title"])
        if "qsport" in it["snippet"]["title"].lower():
            found["qsport"] = it["id"]

def resolve_setanta(s):
    """Setanta Sports Premier League: rus tilida «Команда VS Команда - Обзор» roliklari. Handle noma'lum bo'lsa — bir marta qidiruv (maks 3 urinish)."""
    found = s.setdefault("channels", {})
    if "setanta" in found or s.get("setanta_tries", 0) >= 3:
        return
    s["setanta_tries"] = s.get("setanta_tries", 0) + 1
    def ok(title):
        t = title.lower()
        return "setanta" in t and "premier" in t
    try:
        for h in ("SetantaSportsPremierLeague", "SetantaSportsPL"):
            r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                             params={"key": YT_KEY, "part": "snippet", "forHandle": "@" + h}, timeout=30).json()
            for it in r.get("items", []):
                print("YT CHANNEL setanta ->", it["id"], it["snippet"]["title"])
                if ok(it["snippet"]["title"]):
                    found["setanta"] = it["id"]
                    return
        r = requests.get("https://www.googleapis.com/youtube/v3/search",
                         params={"key": YT_KEY, "part": "snippet", "type": "channel", "q": "Setanta Sports Premier League",
                                 "maxResults": 5}, timeout=30).json()
        for it in r.get("items", []):
            print("YT SEARCH setanta ->", it["snippet"]["channelId"], it["snippet"]["title"])
            if ok(it["snippet"]["title"]):
                found["setanta"] = it["snippet"]["channelId"]
                return
    except Exception as e:
        print("YT CHANNEL ERROR setanta", e)

def channels_for(s, code):
    ids = [cid for cid, (_, codes) in OFFICIAL_CHANNELS.items() if code in codes]
    if s.get("channels", {}).get(code):
        ids.append(s["channels"][code])
    for extra in ("qsport", "setanta"):
        if s.get("channels", {}).get(extra):
            ids.append(s["channels"][extra])
    return ids

_RU = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                ["a","b","v","g","d","e","e","zh","z","i","i","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","sch","","y","","e","yu","ya"]))
# Rus nomlari qisqa -> lotin kalit (translit mos kelmaydigan klublar uchun)
RU_ALIASES = {"бавария": "bayern", "псж": "psg", "псв": "psv", "боруссия дортмунд": "dortmund", "боруссия д": "dortmund",
              "боруссия м": "gladbach", "байер": "leverkusen", "тоттенхэм": "tottenham", "тоттенхем": "tottenham",
              "ювентус": "juventus", "атлетико": "atletico", "атлетик": "athletic", "интер": "inter", "милан": "milan",
              "рома": "roma", "лацио": "lazio", "зальцбург": "salzburg", "црвена звезда": "crvena", "црвена звезда": "red star",
              "ньюкасл": "newcastle", "эвертон": "everton", "вест хэм": "west ham", "брюгге": "brugge", "бенфика": "benfica",
              "спортинг": "sporting", "порту": "porto", "аякс": "ajax", "фейеноорд": "feyenoord", "олимпиакос": "olympiacos",
              "галатасарай": "galatasaray", "фенербахче": "fenerbahce", "бешикташ": "besiktas", "базель": "basel",
              "шахтер": "shakhtar", "динамо киев": "dynamo kyiv", "лейпциг": "leipzig", "айнтрахт": "frankfurt",
              "лилль": "lille", "ницца": "nice", "марсель": "marseille", "лион": "lyon", "монако": "monaco", "ланс": "lens",
              "селтик": "celtic", "рейнджерс": "rangers", "кайрат": "kairat", "бодо глимт": "bodo", "вильярреал": "villarreal",
              "севилья": "sevilla", "валенсия": "valencia", "реал сосьедад": "real sociedad", "реал мадрид": "real madrid",
              "барселона": "barcelona", "ливерпуль": "liverpool", "арсенал": "arsenal", "челси": "chelsea",
              "манчестер сити": "manchester city", "манчестер юнайтед": "manchester united", "наполи": "napoli",
              "аталанта": "atalanta", "фулхэм": "fulham", "фулхем": "fulham", "вулверхэмптон": "wolverhampton",
              "вулверхемптон": "wolverhampton", "борнмут": "bournemouth", "брайтон": "brighton", "брентфорд": "brentford",
              "кристал пэлас": "crystal palace", "лидс": "leeds", "лестер": "leicester", "ноттингем форест": "nottingham",
              "ноттингем": "nottingham", "саутгемптон": "southampton", "сандерленд": "sunderland", "бернли": "burnley",
              "ипсвич": "ipswich", "вест хэм": "west ham", "вест хем": "west ham", "астон вилла": "aston villa",
              "ньюкасл юнайтед": "newcastle", "манчестер юнайтед": "manchester united", "ман сити": "manchester city",
              "ман юнайтед": "manchester united", "болонья": "bologna", "фиорентина": "fiorentina", "штутгарт": "stuttgart"}

def _translit(txt):
    return "".join(_RU.get(ch, ch) for ch in norm(txt))

def _ru_team_ok(ru_name, en_name):
    """Rus nomi ("Реал Мадрид") inglizcha nomga ("Real Madrid") mos keladimi."""
    from difflib import SequenceMatcher
    ru = " ".join(norm(ru_name).replace("-", " ").split())
    keys = set(team_keys(en_name)) | {norm(en_name)}
    for k, v in RU_ALIASES.items():
        k = norm(k)  # norm() "й"→"и", "ё"→"е" qiladi — kalitlarni ham shunday qilamiz
        if ru == k or ru.startswith(k):  # nom jadvalda bor — faqat shunga qarab hal qilamiz (City/United adashmasligi uchun)
            return any(v in key for key in keys)
    tr = _translit(ru)
    return any(tr == key or SequenceMatcher(None, tr, key).ratio() >= 0.85 for key in keys)

def ru_title_match(title, m):
    """Qsport: «Реал Мадрид – ПСВ. Обзор матча Лиги чемпионов. 24.11.2026»."""
    t = norm(title)
    if "обзор" not in t:
        return False
    head = re.split(r"\s+[–—-]\s+(?=обзор)|\.\s", title, maxsplit=1, flags=re.I)[0]
    parts = re.split(r"\s+(?:vs\.?|[–—-])\s+", head, flags=re.I)
    if len(parts) != 2:
        return False
    a, b = parts
    return ((_ru_team_ok(a, m["home"]) and _ru_team_ok(b, m["away"])) or
            (_ru_team_ok(a, m["away"]) and _ru_team_ok(b, m["home"])))

def find_video(m, s):
    """Ищет обзор только на официальных каналах: в названии обе команды (с учётом сокращений),
    ролик опубликован после конца матча, это не превью/пресс-конференция."""
    after = m["end"] - timedelta(hours=1)
    hk, ak = team_keys(m["home"]), team_keys(m["away"])
    for ch_id in channels_for(s, m["code"]):
        for title, pub, vid in uploads(ch_id, pages=4):
            try:
                when = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                continue
            t = norm(title)
            if when < after or any(w in t for w in SKIP_WORDS):
                continue
            if ru_title_match(title, m):
                return f"https://www.youtube.com/watch?v={vid}"
            if not ("highlight" in t or re.search(r"\d\s*[-–:]\s*\d", t)):
                continue
            if any(k in t for k in hk) and any(k in t for k in ak):
                return f"https://www.youtube.com/watch?v={vid}"
    # Diagnostika: topilmasa, kanaldagi so'nggi sarlavhalarni holatga yozamiz (nima uchun mos kelmaganini ko'rish uchun)
    try:
        recent = []
        for ch_id in channels_for(s, m["code"]):
            recent += [f"{pub[5:16]} {title}" for title, pub, _ in uploads(ch_id, pages=1)[:12]]
        dbg = s.setdefault("debug_miss", {})
        dbg[m["id"]] = {"match": f"{m['home']} - {m['away']}", "keys": [hk, ak], "recent": recent[:12]}
        for k in list(dbg)[:-4]:
            dbg.pop(k)
    except Exception as e:
        print("DEBUG MISS xato:", e)
    return None

def text(m, url):
    """Video Telegramning o'zida tepada o'ynaydi (link_preview_options), pastda — matn va kanal logotipi/havolasi."""
    return (f"🎬 <b>{html.escape(m['home'])} {m['hg']}:{m['ag']} {html.escape(m['away'])}</b>\n"
            f"🏆 {m['league']}\n"
            f"▶️ O'yin sharhi\n\n{_channel_footer()}")

WELCOME = ("👋 Salom! Bu <b>FUTBOL OLAMI</b> kanalining boti.\n\n"
           "Reklama, hamkorlik yoki savollar bo'yicha xabaringizni shu yerga yozing — admin javob beradi.")

def handle_contact(s, msg):
    """Bot orqali aloqa: foydalanuvchi yozadi -> admin shaxsiyga keladi; admin shu xabarga reply qilsa -> foydalanuvchiga botdan boradi."""
    chat = msg.get("chat", {})
    if chat.get("type") != "private" or not msg.get("from") or msg["from"].get("is_bot"):
        return
    uid, text = str(msg["from"]["id"]), msg.get("text") or ""
    c = s.setdefault("contact", {})
    cmap = c.setdefault("map", {})
    if uid == str(ADMIN_ID) and text.split("@")[0].lower().startswith("/video"):
        parts = text.split()
        kind = parts[1].lower() if len(parts) > 1 else "skills"
        import daily_videos
        ok, info = daily_videos.send_now(kind)
        tg("sendMessage", chat_id=ADMIN_ID, text=info)
        return
    if uid == str(ADMIN_ID):
        rep = msg.get("reply_to_message")
        target = cmap.get(str(rep["message_id"])) if rep else None
        if target:
            r = tg("copyMessage", chat_id=target, from_chat_id=chat["id"], message_id=msg["message_id"])
            tg("sendMessage", chat_id=ADMIN_ID, reply_to_message_id=msg["message_id"],
               text="✅ Javob yuborildi" if r.get("ok") else "❌ Yuborilmadi (foydalanuvchi botni bloklagan bo'lishi mumkin)")
        elif text.startswith("/start") or cmap:
            # reply qilinmagan oddiy xabar: hech kimga yuborilmaydi — qanday javob berishni eslatamiz
            tg("sendMessage", chat_id=ADMIN_ID, reply_to_message_id=msg["message_id"],
               text="↩️ Javob foydalanuvchiga ketishi uchun uning xabariga (yoki ✉️ sarlavhaga) <b>reply</b> qiling: xabarni bosib turing → «Ответить».",
               parse_mode="HTML")
        return
    if text.startswith("/start"):
        tg("sendMessage", chat_id=chat["id"], text=WELCOME, parse_mode="HTML")
        return
    u = msg["from"]
    name = html.escape(" ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or "—", quote=False)
    handle = f" @{html.escape(u['username'], quote=False)}" if u.get("username") else ""
    hdr = f"✉️ <b>{name}</b>{handle} (id {uid})\n↩️ Javob berish uchun shu xabarga yoki pastdagisiga <b>reply</b> qiling"
    sent_ids = []
    for r in (tg("sendMessage", chat_id=ADMIN_ID, text=hdr, parse_mode="HTML"),
              tg("forwardMessage", chat_id=ADMIN_ID, from_chat_id=chat["id"], message_id=msg["message_id"])):
        if r.get("ok"):
            cmap[str(r["result"]["message_id"])] = chat["id"]
            sent_ids.append(1)
    for k in list(cmap)[:-400]:
        cmap.pop(k)
    last = c.setdefault("ack", {})
    if sent_ids and time.time() - last.get(uid, 0) > 600:  # tasdiq xabari — har 10 daqiqada ko'pi bilan bir marta
        last[uid] = time.time()
        tg("sendMessage", chat_id=chat["id"], text="✅ Xabaringiz adminga yuborildi. Tez orada javob beramiz.")

def handle_buttons(s):
    # Vercel-бот удалён: если у бота остался webhook, getUpdates вернёт 409 и кнопки не сработают
    tg("deleteWebhook", drop_pending_updates=False)
    ups = tg("getUpdates", offset=s["offset"], timeout=0, allowed_updates=["callback_query", "message"]).get("result", [])
    for u in ups:
        s["offset"] = u["update_id"] + 1
        if u.get("message"):
            try:
                handle_contact(s, u["message"])
            except Exception as e:
                print("CONTACT xato:", e)
            continue
        q = u.get("callback_query")
        if not q or str(q["from"]["id"]) != str(ADMIN_ID):
            continue
        action, mid = q["data"].split(":", 1)
        item = s["offered"].get(mid)
        if action == "pub" and item and not item.get("done"):
            if item.get("news"):
                send_news(CHANNEL_ID, item["text"], item.get("image", ""))
                if GROUP_ID:
                    send_news(GROUP_ID, item["text"], item.get("image", ""))
            else:
                video = item.get("video")
                if video:  # yangi format: video tepada o'ynaydi, matn pastda
                    send_news(CHANNEL_ID, item["text"], video)
                    if GROUP_ID:
                        send_news(GROUP_ID, item["text"], video)
                else:  # eski (kutib turgan) takliflar
                    tg("sendMessage", chat_id=CHANNEL_ID, text=item["text"], parse_mode="HTML")
                    if GROUP_ID:
                        tg("sendMessage", chat_id=GROUP_ID, text=item["text"], parse_mode="HTML")
            item["done"] = "published"
            note = "✅ Kanalga joylandi"
        else:
            if item: item["done"] = "skipped"
            note = "❌ O'tkazib yuborildi"
        tg("answerCallbackQuery", callback_query_id=q["id"], text=note)
        tg("editMessageReplyMarkup", chat_id=q["message"]["chat"]["id"],
           message_id=q["message"]["message_id"], reply_markup={"inline_keyboard": []})

# ---------- Kirill -> Lotin ----------
_MAP = {"а":"a","б":"b","в":"v","г":"g","ғ":"g‘","д":"d","ё":"yo","ж":"j","з":"z","и":"i",
        "й":"y","к":"k","қ":"q","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s",
        "т":"t","у":"u","ў":"o‘","ф":"f","х":"x","ҳ":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sh",
        "ъ":"ʼ","ы":"i","ь":"","э":"e","ю":"yu","я":"ya"}
_VOW = set("аеёиоуўэюяaeiou")

def lotin(text):
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        prev = text[i - 1].lower() if i else " "
        if low == "е":
            r = "ye" if (not prev.isalpha() or prev in _VOW or prev in "ъь") else "e"
        elif low in _MAP:
            r = _MAP[low]
        else:
            out.append(ch); continue
        if ch.isupper() and r:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            r = r.upper() if (nxt.isupper() or (prev.isupper() and not nxt.isalpha())) else r[0].upper() + r[1:]
        out.append(r)
    return "".join(out)

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

# Зарубежные сайты (английский). Новости переводятся на узбекский (латиница) и приходят тебе в личку.
FOREIGN_FEEDS = {
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "The Guardian": "https://www.theguardian.com/football/rss",
    "ESPN": "https://www.espn.com/espn/rss/soccer/news",
}
FOREIGN_ENABLED = False  # зарубежные новости ОТКЛЮЧЕНЫ (плохой перевод, ссылки на чужие сайты). True — включить обратно
FOREIGN_PER_RUN = 2  # сколько зарубежных новостей присылать за один раз (каждые 30 минут)

def tarjima(t):
    """Перевод на узбекский (латиница) через бесплатный Google Translate. При ошибке — оригинал."""
    if not t:
        return t
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "auto", "tl": "uz", "dt": "t", "q": t[:1500]},
                         timeout=20)
        out = "".join(p[0] for p in r.json()[0] if p and p[0])
        return out or t
    except Exception as e:
        print("TARJIMA xato:", e)
        return t

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
        full = it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
        img = ""
        for tag in ("enclosure", "{http://search.yahoo.com/mrss/}content", "{http://search.yahoo.com/mrss/}thumbnail"):
            el = it.find(tag)
            if el is not None and el.get("url") and (el.get("type", "image").startswith("image")):
                img = el.get("url"); break
        if not img:
            m_ = re.search(r'<img[^>]+src=["\']([^"\']+)', (full or it.findtext("description") or ""))
            img = m_.group(1) if m_ else ""
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            dt = None
        if title and link:
            items.append({"source": name, "title": lotin(title), "link": link, "desc": lotin(desc), "dt": dt,
                          "full": lotin(_paras(full)) if full else "", "image": img})
    print("NEWS", name, len(items), "ta")
    return items

def is_football(n):
    if n["source"] == "sports.uz" or n["source"] in FOREIGN_FEEDS:
        return True
    text_ = (n["title"] + " " + n["desc"]).lower()
    return any(w in text_ for w in FOOTBALL_WORDS)

_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "figure", "button"}

class _ArticleParser(HTMLParser):
    """Sahifadan <article> (bo'lmasa butun sahifa) ichidagi abzatslar va og:image."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.image, self.skip, self.in_article, self.in_p = "", 0, 0, False
        self.art, self.allp, self.cur = [], [], []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:image" and not self.image:
            self.image = a.get("content", "")
        if tag in _SKIP_TAGS:
            self.skip += 1
        if tag == "article":
            self.in_article += 1
        if tag == "p" and not self.skip:
            self.in_p, self.cur = True, []
    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self.skip:
            self.skip -= 1
        if tag == "article" and self.in_article:
            self.in_article -= 1
        if tag == "p" and self.in_p:
            self.in_p = False
            t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
            if t:
                self.allp.append(t)
                if self.in_article:
                    self.art.append(t)
    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.cur.append(data)

_JUNK = ("cookie", "obuna bo", "obuna bo‘l", "подпис", "реклама", "reklama", "©", "barcha huquqlar", "telegram kanal")

def _paras(htm):
    """HTML (RSS content:encoded) -> abzatslar, har biri alohida qatorda."""
    parts = re.findall(r"<p[^>]*>(.*?)</p>", htm, flags=re.S | re.I) or [htm]
    return "\n\n".join(t for t in (clean(x) for x in parts) if len(t) > 3)

def fetch_article(link):
    """(matn, rasm) — maqola sahifasidan to'liq matn. Xato bo'lsa ("", "")."""
    try:
        r = requests.get(link, timeout=30, headers={"User-Agent": "Mozilla/5.0 FutbolOlamiBot"})
        r.encoding = r.encoding or "utf-8"
        p = _ArticleParser()
        p.feed(r.text)
    except Exception as e:
        print("ARTICLE xato:", link, e)
        return "", ""
    paras = [t for t in (p.art or p.allp) if len(t) > 40 and not any(j in t.lower() for j in _JUNK)]
    return "\n\n".join(paras), p.image

def _channel_footer():
    try:
        from post_results import channel_info
        link, _ = channel_info()
    except Exception as e:
        print("CHANNEL INFO xato:", e)
        link = ""
    return f'👉 <a href="{html.escape(link)}">FUTBOL OLAMI</a> 👈' if link else "<b>FUTBOL OLAMI</b>"

MAX_BODY = 3300  # Telegram: xabar 4096 belgigacha

def news_text(n):
    """Butun yangilik matni Telegramning o'zida (saytga havolasiz). Qaytaradi: (matn, rasm_url)."""
    body, image = n.get("full") or "", n.get("image") or ""
    if len(body) < 300:  # RSS'da qisqa — sahifadan to'liq matnni olamiz
        page, pimg = fetch_article(n["link"])
        if len(page) > len(body):
            body = lotin(page) if re.search(r"[А-Яа-яЎўҚқҒғҲҳ]", page) else page
        image = image or pimg
    if len(body) < 80:
        body = n["desc"] or body
    paras, total = [], 0
    for para in [x.strip() for x in body.split("\n\n") if x.strip()]:
        if paras and para.strip() == paras[-1]:
            continue
        if total + len(para) > MAX_BODY:
            if not paras:
                paras.append(para[:MAX_BODY].rsplit(" ", 1)[0] + "…")
            break
        paras.append(para)
        total += len(para)
    if paras and paras[0].strip().lower() == n["title"].strip().lower():
        paras = paras[1:]
    text = f"📰 <b>{html.escape(n['title'], quote=False)}</b>\n\n"
    if paras:
        text += "\n\n".join(html.escape(x, quote=False) for x in paras) + "\n\n"
    text += _channel_footer()
    if image:  # rasm — xabar tepasida katta ko'rinadi (ko'rinmas havola orqali)
        text = f'<a href="{html.escape(image)}">&#8203;</a>' + text
    return text, image

def send_news(chat_id, text, image, small=False, **extra):
    opts = {"url": image, "prefer_large_media": True, "show_above_text": True} if image else {"is_disabled": True}
    if image and not small and "youtu" in image and image not in text:
        # havola matnda (ko'rinmas) bo'lsin: aks holda Telegram ba'zan video kartochkasini qurmay, faqat matn qoldiradi
        text = f'<a href="{html.escape(image)}">&#8203;</a>' + text
    if image and small:  # YouTube-sharh: ixcham ko'rinish (kichik rasm yonida), joy kam egallanadi
        opts = {"url": image, "prefer_small_media": True, "show_above_text": True}
        if image not in text:  # havola matnda bo'lsin (ko'rinmas), shunda Telegram oldindan ko'rinishni aniq quradi
            text = f'<a href="{html.escape(image)}">&#8203;</a>' + text
    return tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", link_preview_options=opts, **extra)

def offer_news(s):
    _offer(s, FEEDS, "news_init", NEWS_PER_RUN, foreign=False)
    if FOREIGN_ENABLED:
        _offer(s, FOREIGN_FEEDS, "foreign_init", FOREIGN_PER_RUN, foreign=True)

def _offer(s, feeds, init_key, per_run, foreign):
    seen = s.setdefault("news_seen", [])
    first_run = not s.get(init_key)
    all_news = []
    for name, url in feeds.items():
        all_news += [n for n in read_feed(name, url) if is_football(n)]
    now = datetime.now(TASHKENT)
    fresh = []
    for n in all_news:
        key = "n" + hashlib.md5(n["link"].encode()).hexdigest()[:10]
        if key in seen or any(f["key"] == key for f in fresh):
            continue
        if not n["dt"]:
            continue  # sanasi noma'lum — eski bo'lishi mumkin
        if TEST:
            if now - n["dt"] > timedelta(days=7):
                continue
        elif n["dt"].astimezone(TASHKENT).date() != now.date():
            continue  # faqat bugungi yangiliklar
        n["key"] = key
        fresh.append(n)
    if first_run and not TEST:
        # Birinchi ishga tushishda eski yangiliklarni yubormaymiz, faqat eslab qolamiz
        seen += [n["key"] for n in fresh]
        s[init_key] = True
        print("NEWS: birinchi ishga tushish,", len(fresh), "ta yangilik eslab qolindi")
        return
    for n in fresh[:2 if TEST else per_run]:
        if foreign:
            n["title"], n["desc"] = tarjima(n["title"]), tarjima(n["desc"])
        t, image = news_text(n)
        send_news(ADMIN_ID, t, image,
                  reply_markup={"inline_keyboard": [[{"text": "✅ Kanalga", "callback_data": f"pub:{n['key']}"},
                                                     {"text": "❌ Kerak emas", "callback_data": f"skip:{n['key']}"}]]})
        s["offered"][n["key"]] = {"text": t, "image": image, "news": True}
        seen.append(n["key"])
    s[init_key] = True
    s["news_seen"] = seen[-2000:]

def offer_new(s):
    now = datetime.now(TASHKENT)
    resolve_channels(s)
    videos = s.setdefault("videos", {})
    sent = 0
    for m in finished_matches():
        if TEST and sent >= 2:
            break
        if (m["id"] in videos or m["id"] in s["offered"]) and not TEST:
            continue
        if now - m["end"] > timedelta(days=8 if TEST else 1):
            continue
        if not channels_for(s, m["code"]):
            continue
        tries = s.setdefault("tries", {})
        if tries.get(m["id"], 0) >= MAX_TRIES and not TEST:
            continue
        tries[m["id"]] = tries.get(m["id"], 0) + 1
        url = find_video(m, s)
        if not url:
            continue
        t = text(m, url)
        # Tasdiqsiz: sharh to'g'ridan-to'g'ri kanalga (va guruhga) chiqadi, video Telegramning o'zida o'ynaydi
        r = send_news(CHANNEL_ID, t, url)
        if not r.get("ok"):
            continue  # keyingi ishga tushirishda qayta uriniladi
        if GROUP_ID:
            send_news(GROUP_ID, t, url)
        videos[m["id"]] = url  # jadvallarda "Obzor" havolasi sifatida ham ishlatiladi
        s["offered"][m["id"]] = {"text": t, "video": url, "done": "published"}
        sent += 1

if __name__ == "__main__":
    import traceback
    s = load()
    # ONLY_BUTTONS=1 — только обработать нажатия кнопок (быстро, без YouTube и новостей)
    steps = (handle_buttons,) if os.environ.get("ONLY_BUTTONS") == "1" else (handle_buttons, offer_new, offer_news)
    for step in steps:
        try:
            step(s)
        except Exception:
            # Одна ошибка не должна останавливать остальные этапы и сохранение состояния
            print("STEP FAILED:", step.__name__)
            traceback.print_exc()
    save(s)
