import os
import json
import html
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")
API_URL = "https://v3.football.api-sports.io"
TASHKENT = ZoneInfo("Asia/Tashkent")
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

LEAGUE_IDS = {
    39: "ANGLIYA — PREMIER LIGA",
    140: "ISPANIYA — LA LIGA",
    135: "ITALIYA — SERIE A",
    78: "GERMANIYA — BUNDESLIGA",
    61: "FRANSIYA — LIGUE 1",
    2: "CHEMPIONLAR LIGASI",
    3: "YEVROPA LIGASI",
    848: "KONFERENSIYALAR LIGASI",
}


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def api_get(endpoint, params):
    r = requests.get(
        f"{API_URL}/{endpoint}",
        headers={"x-apisports-key": API_KEY, "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise Exception(str(data["errors"]))
    return data.get("response", [])


def selected_fixtures(date_string):
    fixtures = api_get("fixtures", {"date": date_string, "timezone": "Asia/Tashkent"})
    result = []
    for m in fixtures:
        league = m.get("league", {})
        lid = league.get("id")
        country = league.get("country", "")
        if lid in LEAGUE_IDS:
            m["display_league"] = LEAGUE_IDS[lid]
            result.append(m)
        elif country == "Uzbekistan":
            m["display_league"] = "O‘ZBEKISTON — " + league.get("name", "FUTBOL")
            result.append(m)
    result.sort(key=lambda x: (x.get("display_league", ""), x.get("fixture", {}).get("date", "")))
    return result


def crest(url, size=54):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        im = Image.open(BytesIO(r.content)).convert("RGBA")
        im.thumbnail((size, size), Image.Resampling.LANCZOS)
        return im
    except Exception:
        return None


def fit_text(draw, text, max_width, start_size, min_size=16, bold=False):
    size = start_size
    while size > min_size:
        f = font(size, bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
        size -= 1
    return font(min_size, bold)


def make_card(title, date_string, matches):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), (5, 15, 29))
    d = ImageDraw.Draw(img, "RGBA")

    # Background
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=(4 + int(3*t), 14 + int(12*t), 28 + int(22*t), 255))
    for x in range(-500, W + 500, 170):
        d.polygon([(x, 0), (x+55, 0), (x-260, H), (x-315, H)], fill=(20, 100, 170, 22))
    d.ellipse((70, 1050, 1010, 1500), fill=(8, 65, 95, 70))
    d.line((70, 1120, 1010, 1120), fill=(50, 160, 220, 100), width=2)

    # Header
    d.ellipse((45, 40, 150, 145), fill=(8, 100, 180, 60), outline=(75, 190, 255, 180), width=3)
    d.ellipse((67, 62, 128, 123), fill=(240, 245, 250, 245))
    d.polygon([(98, 74), (114, 86), (110, 104), (91, 104), (86, 86)], fill=(15, 25, 40, 255))
    d.text((175, 52), "FUTBOL OLAMI", font=font(55, True), fill=(245, 250, 255, 255))
    d.text((178, 112), "Futbol haqida hammasi!", font=font(23), fill=(150, 215, 245, 255))

    date = datetime.strptime(date_string, "%Y-%m-%d")
    day = date.strftime("%d")
    months = ["YANVAR", "FEVRAL", "MART", "APREL", "MAY", "IYUN", "IYUL", "AVGUST", "SENTABR", "OKTABR", "NOYABR", "DEKABR"]
    weekdays = ["DUSHANBA", "SESHANBA", "CHORSHANBA", "PAYSHANBA", "JUMA", "SHANBA", "YAKSHANBA"]

    d.rounded_rectangle((45, 190, 215, 330), 18, fill=(245, 250, 255, 250))
    d.rounded_rectangle((45, 190, 215, 235), 18, fill=(235, 55, 55, 255))
    d.rectangle((45, 213, 215, 235), fill=(235, 55, 55, 255))
    d.text((68, 196), months[date.month-1], font=font(21, True), fill=(255,255,255,255))
    d.text((83, 244), day, font=font(64, True), fill=(8, 25, 40, 255))
    d.text((250, 195), title, font=font(40, True), fill=(250,252,255,255))
    d.text((250, 250), f"{date.strftime('%d.%m.%Y')}  |  {weekdays[date.weekday()]}", font=font(22), fill=(155,205,235,255))

    y = 360
    if not matches:
        d.rounded_rectangle((45, y, W-45, y+120), 20, fill=(5, 28, 45, 240), outline=(40, 130, 185, 170), width=2)
        d.text((80, y+38), "Bugun tanlangan musobaqalarda o‘yinlar yo‘q.", font=font(25, True), fill=(240,248,255,255))
    else:
        current = None
        for m in matches:
            league = m.get("display_league", "FUTBOL")
            if league != current:
                current = league
                if y + 62 > 1080:
                    break
                d.rounded_rectangle((45, y, W-45, y+58), 14, fill=(7, 35, 55, 245), outline=(35, 120, 170, 180), width=2)
                d.text((68, y+15), league, font=fit_text(d, league, 850, 24, 17, True), fill=(245,250,255,255))
                y += 63
            if y + 72 > 1080:
                break
            row = (55, y, W-55, y+70)
            d.rounded_rectangle(row, 10, fill=(4, 22, 37, 225))
            fx = m.get("fixture", {})
            status = fx.get("status", {}).get("short", "")
            tm = fx.get("date", "")
            time = tm[11:16] if len(tm) >= 16 else "--:--"
            home = m.get("teams", {}).get("home", {})
            away = m.get("teams", {}).get("away", {})
            hn = home.get("name", "?")
            an = away.get("name", "?")
            hf = crest(home.get("logo"), 46)
            af = crest(away.get("logo"), 46)
            d.text((70, y+23), time, font=font(19, True), fill=(225,240,250,255))
            hf_x, af_x = 420, 650
            if hf: img.paste(hf, (hf_x, y+12), hf)
            if af: img.paste(af, (af_x, y+12), af)
            hfont = fit_text(d, hn, 235, 20, 14)
            afont = fit_text(d, an, 235, 20, 14)
            hb = d.textbbox((0,0), hn, font=hfont)[2]
            d.text((400-hb, y+22), hn, font=hfont, fill=(245,248,252,255))
            d.text((710, y+22), an, font=afont, fill=(245,248,252,255))
            if status in ["FT", "AET", "P"]:
                hs = m.get("goals", {}).get("home")
                ass = m.get("goals", {}).get("away")
                score = f"{hs if hs is not None else 0} : {ass if ass is not None else 0}"
                fill = (20, 80, 120, 230)
            elif status in ["1H", "2H", "HT", "ET", "BT", "P"]:
                hs = m.get("goals", {}).get("home") or 0
                ass = m.get("goals", {}).get("away") or 0
                minute = m.get("fixture", {}).get("status", {}).get("elapsed") or ""
                score = f"LIVE {minute}'  {hs}:{ass}"
                fill = (170, 35, 35, 230)
            else:
                score = "VS"
                fill = (7, 50, 80, 230)
            d.rounded_rectangle((500, y+14, 640, y+56), 10, fill=fill, outline=(50,150,210,150), width=1)
            sb = d.textbbox((0,0), score, font=font(17, True))[2]
            d.text((570-sb/2, y+24), score, font=font(17, True), fill=(255,255,255,255))
            y += 76

    d.text((60, 1160), "Futbol bizni birlashtiradi!", font=font(32, True), fill=(245,250,255,255))
    d.text((60, 1210), "Futbol olami", font=font(29, True), fill=(90,205,255,255))
    d.text((60, 1250), "Futbol haqida hammasi!", font=font(20), fill=(165,210,235,255))
    return img


def send_photo(image, caption):
    bio = BytesIO()
    image.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": CHANNEL_ID, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("futbol-olami.png", bio, "image/png")},
        timeout=30,
    )
    result = r.json()
    if not result.get("ok"):
        raise Exception(str(result))


def run_bot():
    now = datetime.now(TASHKENT)
    today = now.date()
    yesterday = today - timedelta(days=1)
    for date_obj, title in [
        (yesterday, "KECHAGI O‘YINLAR NATIJALARI"),
        (today, "BUGUNGI O‘YINLAR"),
    ]:
        date_string = date_obj.strftime("%Y-%m-%d")
        matches = selected_fixtures(date_string)
        image = make_card(title, date_string, matches)
        send_photo(image, "⚽ <b>FUTBOL OLAMI</b>\nFutbol haqida hammasi!")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not CRON_SECRET or self.headers.get("authorization", "") != f"Bearer {CRON_SECRET}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return
        try:
            run_bot()
            body = json.dumps({"ok": True, "message": "Futbol olami image cron completed"}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"CRON ERROR: {e}")
            body = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
