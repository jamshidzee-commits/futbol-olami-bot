import os
import json
import html
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
TEST_MODE = os.environ.get("TEST_MODE", "false") == "true"

TASHKENT = ZoneInfo("Asia/Tashkent")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"
SENT_FILE = "sent.json"
W = 1080
MAX_MATCHES = 5

HERE = os.path.dirname(os.path.abspath(__file__))
REGULAR = os.path.join(HERE, "fonts", "DejaVuSans.ttf")
BOLD = os.path.join(HERE, "fonts", "DejaVuSans-Bold.ttf")

LEAGUES = {
    "eng.1": "ANGLIYA — PREMIER LIGA",
    "esp.1": "ISPANIYA — LA LIGA",
    "ita.1": "ITALIYA — SERIYA A",
    "ger.1": "GERMANIYA — BUNDESLIGA",
    "fra.1": "FRANSIYA — LIGUE 1",
    "uefa.champions": "UEFA — CHEMPIONLAR LIGASI",
    "uefa.europa": "UEFA — YEVROPA LIGASI",
    "uefa.europa.conf": "UEFA — KONFERENSIYALAR LIGASI",
}

MONTHS = {1: "YANVAR", 2: "FEVRAL", 3: "MART", 4: "APREL", 5: "MAY", 6: "IYUN",
          7: "IYUL", 8: "AVGUST", 9: "SENTABR", 10: "OKTABR", 11: "NOYABR", 12: "DEKABR"}
DAYS = {0: "DUSHANBA", 1: "SESHANBA", 2: "CHORSHANBA", 3: "PAYSHANBA",
        4: "JUMA", 5: "SHANBA", 6: "YAKSHANBA"}

SHORT = {
    "Manchester United": "Man United", "Manchester City": "Man City",
    "Tottenham Hotspur": "Tottenham", "Wolverhampton Wanderers": "Wolves",
    "Newcastle United": "Newcastle", "West Ham United": "West Ham",
    "Nottingham Forest": "Nott'm Forest", "Paris Saint-Germain": "PSG",
    "Bayern Munich": "Bayern", "Athletic Club": "Athletic",
}

logo_cache = {}


def F(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


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
    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
    return {
        "id": ev["id"],
        "dt": dt,
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_logo": home["team"].get("logo"),
        "away_logo": away["team"].get("logo"),
        "hg": int(float(home.get("score", 0) or 0)),
        "ag": int(float(away.get("score", 0) or 0)),
        "note": {"STATUS_FINAL_AET": "QO'SHIMCHA VAQT",
                 "STATUS_FINAL_PEN": "PENALTILAR"}.get(status.get("name"), ""),
    }


def get_logo(url):
    if not url:
        return None
    if url in logo_cache:
        return logo_cache[url]
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail((80, 80), Image.Resampling.LANCZOS)
        logo_cache[url] = img
        return img
    except Exception as e:
        print("LOGO ERROR:", e)
        logo_cache[url] = None
        return None


def draw_logo(img, url, cx, cy, size=64):
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2),
              fill=(7, 30, 47, 255), outline=(48, 145, 200, 220), width=2)
    logo = get_logo(url)
    if logo:
        p = logo.copy()
        p.thumbnail((size - 10, size - 10), Image.Resampling.LANCZOS)
        img.alpha_composite(p, (int(cx - p.width / 2), int(cy - p.height / 2)))


def fit_text(d, text, max_width, start=24, minimum=15):
    text = SHORT.get(text, text)
    for size in range(start, minimum - 1, -1):
        f = F(size, True)
        box = d.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return text, f
    f = F(minimum, True)
    t = text
    while len(t) > 3:
        cand = t[:-1] + "..."
        box = d.textbbox((0, 0), cand, font=f)
        if box[2] - box[0] <= max_width:
            return cand, f
        t = t[:-1]
    return t, f


def draw_match(img, y, m):
    d = ImageDraw.Draw(img, "RGBA")
    hn, hf = fit_text(d, m["home"], 225)
    an, af = fit_text(d, m["away"], 260)

    d.rounded_rectangle((45, y, W - 45, y + 116), 18, fill=(6, 27, 44, 250),
                        outline=(38, 120, 165, 220), width=2)
    d.text((70, y + 43), m["dt"].strftime("%H:%M"), font=F(25, True), fill=(240, 248, 252, 255))

    hb = d.textbbox((0, 0), hn, font=hf)
    d.text((405 - (hb[2] - hb[0]), y + 44), hn, font=hf, fill=(248, 251, 255, 255))
    draw_logo(img, m["home_logo"], 440, y + 58)
    draw_logo(img, m["away_logo"], 640, y + 58)
    d.text((680, y + 44), an, font=af, fill=(248, 251, 255, 255))

    d.rounded_rectangle((490, y + 27, 590, y + 88), 13, fill=(8, 58, 84, 255),
                        outline=(55, 160, 215, 230), width=2)
    center = f"{m['hg']} : {m['ag']}"
    box = d.textbbox((0, 0), center, font=F(24, True))
    d.text((540 - (box[2] - box[0]) / 2, y + 41), center, font=F(24, True), fill=(255, 255, 255, 255))

    if m["note"]:
        nb = d.textbbox((0, 0), m["note"], font=F(13, True))
        d.text((540 - (nb[2] - nb[0]) / 2, y + 94), m["note"], font=F(13, True), fill=(130, 205, 245, 255))


def make_image(title, dt, groups, page_no, total_pages):
    count = sum(len(ms) for _, ms in groups)
    height = 430 + len(groups) * 100 + count * 150 + 160
    img = Image.new("RGBA", (W, height), (5, 16, 29, 255))
    d = ImageDraw.Draw(img, "RGBA")

    for yy in range(height):
        ratio = yy / max(1, height - 1)
        d.line((0, yy, W, yy), fill=(int(5 + 3 * ratio), int(17 + 10 * ratio), int(30 + 18 * ratio), 255))
    for x in range(-250, W + 400, 190):
        d.polygon([(x, 0), (x + 65, 0), (x - 170, 250), (x - 235, 250)], fill=(25, 125, 190, 30))

    d.ellipse((55, 42, 155, 142), fill=(10, 72, 112, 110), outline=(70, 185, 240, 230), width=3)
    d.text((82, 59), "F", font=F(50, True), fill=(255, 255, 255, 255))
    d.text((185, 55), "FUTBOL OLAMI", font=F(48, True), fill=(245, 250, 255, 255))
    d.text((188, 112), "Futbol haqida hammasi!", font=F(21), fill=(130, 205, 245, 255))

    d.rounded_rectangle((55, 180, 205, 320), 20, fill=(245, 249, 252, 255))
    d.rounded_rectangle((55, 180, 205, 224), 20, fill=(235, 55, 55, 255))
    d.rectangle((55, 205, 205, 224), fill=(235, 55, 55, 255))
    d.text((78, 186), MONTHS[dt.month], font=F(17, True), fill=(255, 255, 255, 255))
    d.text((88, 228), dt.strftime("%d"), font=F(58, True), fill=(8, 25, 40, 255))
    d.text((245, 188), title, font=F(33, True), fill=(248, 252, 255, 255))
    d.text((248, 245), f"{dt.strftime('%d.%m.%Y')} | {DAYS[dt.weekday()]}", font=F(19), fill=(145, 200, 230, 255))

    if total_pages > 1:
        d.rounded_rectangle((900, 188, 1018, 242), 16, fill=(7, 105, 155, 235))
        d.text((926, 200), f"{page_no}/{total_pages}", font=F(20, True), fill=(255, 255, 255, 255))

    y = 355
    for league, matches in groups:
        d.rounded_rectangle((45, y, W - 45, y + 70), 18, fill=(7, 39, 62, 255),
                            outline=(45, 140, 195, 230), width=2)
        d.text((70, y + 20), league, font=F(23, True), fill=(248, 252, 255, 255))
        y += 88
        for m in matches:
            draw_match(img, y, m)
            y += 150
        y += 12

    fy = height - 145
    d.line((60, fy, W - 60, fy), fill=(55, 135, 175, 150), width=2)
    d.text((70, fy + 25), "Futbol bizni birlashtiradi!", font=F(27, True), fill=(238, 248, 255, 255))
    d.text((70, fy + 72), "Futbol olami  •  Futbol haqida hammasi!", font=F(20), fill=(125, 195, 225, 255))
    return img.convert("RGB")


def paginate(items):
    """items: list of (league, match). Returns pages of [(league, [matches])]."""
    pages, current, count = [], [], 0
    for league, m in items:
        if count >= MAX_MATCHES:
            pages.append(current)
            current, count = [], 0
        if current and current[-1][0] == league:
            current[-1][1].append(m)
        else:
            current.append((league, [m]))
        count += 1
    if current:
        pages.append(current)
    return pages


def send_photo(img, caption):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": CHANNEL_ID, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("futbol-olami.jpg", buf, "image/jpeg")},
        timeout=30,
    )
    print("TELEGRAM:", r.status_code, r.text[:200])
    return r.ok


def post(items, title):
    """Send images for a list of (league, match) sorted by time."""
    if not items:
        return []
    pages = paginate(items)
    ok_ids = []
    for no, groups in enumerate(pages, 1):
        dt = groups[0][1][0]["dt"]
        img = make_image(title, dt, groups, no, len(pages))
        caption = f"<b>FUTBOL OLAMI</b>\n{html.escape(title)}\n{dt.strftime('%d.%m.%Y')}"
        if len(pages) > 1:
            caption += f"\nSahifa: {no}/{len(pages)}"
        if send_photo(img, caption):
            ok_ids += [m["id"] for _, ms in groups for m in ms]
    return ok_ids


def main():
    now = datetime.now(TASHKENT)
    days_back = 7 if TEST_MODE else 1
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back, -1, -1)]

    finished, seen = [], set()
    for code, label in LEAGUES.items():
        for d in dates:
            for ev in get_events(code, d):
                m = parse_event(ev)
                if m and m["id"] not in seen:
                    seen.add(m["id"])
                    finished.append((label, m))

    finished.sort(key=lambda x: x[1]["dt"])
    print("FINISHED FOUND:", len(finished))

    if TEST_MODE:
        print("TEST MODE: sending last 3 finished matches")
        post(finished[-3:], "O'YIN NATIJALARI")
        return

    sent = load_sent()
    fresh = [(l, m) for l, m in finished if f"espn-{m['id']}" not in sent]
    if not fresh:
        print("NOTHING NEW")
        return
    for mid in post(fresh, "O'YIN NATIJALARI"):
        sent.add(f"espn-{mid}")
    save_sent(sent)


if __name__ == "__main__":
    main()
