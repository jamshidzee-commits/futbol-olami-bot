import os
import json
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler

from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io"
TASHKENT = ZoneInfo("Asia/Tashkent")

IMAGE_WIDTH = 1080

# Kichik telefonda ham o'qilishi uchun kamroq o'yin.
MAX_MATCHES_PER_IMAGE = 5

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

LEAGUE_IDS = {
    39: "ANGLIYA — PREMIER LIGA",
    140: "ISPANIYA — LA LIGA",
    135: "ITALIYA — SERIYA A",
    78: "GERMANIYA — BUNDESLIGA",
    61: "FRANSIYA — LIGUE 1",
    2: "CHEMPIONLAR LIGASI",
    3: "YEVROPA LIGASI",
    848: "KONFERENSIYALAR LIGASI",
}

logo_cache = {}


def font(size, bold=False):
    return ImageFont.truetype(
        FONT_BOLD if bold else FONT_REGULAR,
        size
    )


def api_get(endpoint, params):
    response = requests.get(
        f"{API_URL}/{endpoint}",
        headers={
            "x-apisports-key": API_KEY,
            "Accept": "application/json"
        },
        params=params,
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    if data.get("errors"):
        raise Exception(str(data["errors"]))

    return data.get("response", [])


def get_matches(date_string):
    fixtures = api_get(
        "fixtures",
        {
            "date": date_string,
            "timezone": "Asia/Tashkent"
        }
    )

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
                "O‘ZBEKISTON — " +
                league.get("name", "FUTBOL").upper()
            )
            result.append(match)

    result.sort(
        key=lambda x: (
            x.get("league_name", ""),
            x.get("fixture", {}).get("date", "")
        )
    )

    return result


def get_logo(url):
    if not url:
        return None

    if url in logo_cache:
        return logo_cache[url]

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail((72, 72), Image.Resampling.LANCZOS)
        logo_cache[url] = img
        return img
    except Exception as e:
        print("LOGO ERROR:", e)
        logo_cache[url] = None
        return None


def draw_logo(image, url, cx, cy, size=66):
    draw = ImageDraw.Draw(image, "RGBA")

    draw.ellipse(
        (cx-size//2, cy-size//2, cx+size//2, cy+size//2),
        fill=(8, 31, 49, 255),
        outline=(45, 145, 200, 230),
        width=2
    )

    logo = get_logo(url)
    if logo:
        copy = logo.copy()
        copy.thumbnail((size-12, size-12), Image.Resampling.LANCZOS)
        x = int(cx - copy.width / 2)
        y = int(cy - copy.height / 2)
        image.alpha_composite(copy, (x, y))


def status_of(match):
    status = (
        match.get("fixture", {})
        .get("status", {})
        .get("short", "")
    )

    if status in ("FT", "AET", "PEN"):
        return "finished"

    if status in ("1H", "2H", "HT", "ET", "BT", "P"):
        return "live"

    return "upcoming"


def match_time(match):
    value = match.get("fixture", {}).get("date", "")
    return value[11:16] if len(value) >= 16 else "--:--"


def short_name(name):
    replacements = {
        "Manchester United": "Man United",
        "Manchester City": "Man City",
        "Tottenham Hotspur": "Tottenham",
        "Wolverhampton Wanderers": "Wolves",
        "Newcastle United": "Newcastle",
        "West Ham United": "West Ham",
        "Nottingham Forest": "Nott'm Forest",
        "Brighton Hove Albion": "Brighton",
        "Paris Saint Germain": "PSG",
        "Bayern Munich": "Bayern",
        "Racing Santander": "Racing",
        "Athletic Club": "Athletic",
    }
    return replacements.get(name, name)


def fit_team_name(draw, name, max_width=280):
    name = short_name(name)

    size = 27
    while size >= 17:
        f = font(size, True)
        box = draw.textbbox((0, 0), name, font=f)
        if box[2] - box[0] <= max_width:
            return name, f
        size -= 1

    f = font(17, True)
    text = name

    while len(text) > 3:
        box = draw.textbbox((0, 0), text + "...", font=f)
        if box[2] - box[0] <= max_width:
            return text + "...", f
        text = text[:-1]

    return text + "...", f


def draw_match(image, y, match):
    draw = ImageDraw.Draw(image, "RGBA")

    home = match.get("teams", {}).get("home", {})
    away = match.get("teams", {}).get("away", {})

    home_name, home_font = fit_team_name(
        draw, home.get("name", "?")
    )
    away_name, away_font = fit_team_name(
        draw, away.get("name", "?")
    )

    # Match card
    draw.rounded_rectangle(
        (55, y, IMAGE_WIDTH-55, y+118),
        20,
        fill=(6, 27, 44, 245),
        outline=(38, 120, 165, 210),
        width=2
    )

    # Time
    draw.text(
        (78, y+43),
        match_time(match),
        font=font(27, True),
        fill=(240, 247, 252, 255)
    )

    # Logos
    draw_logo(
        image,
        home.get("logo"),
        420,
        y+59,
        68
    )
    draw_logo(
        image,
        away.get("logo"),
        660,
        y+59,
        68
    )

    # Team names
    hb = draw.textbbox((0, 0), home_name, font=home_font)
    home_w = hb[2] - hb[0]

    draw.text(
        (390-home_w, y+48),
        home_name,
        font=home_font,
        fill=(250, 252, 255, 255)
    )

    draw.text(
        (695, y+48),
        away_name,
        font=away_font,
        fill=(250, 252, 255, 255)
    )

    state = status_of(match)

    if state == "finished":
        hs = match.get("goals", {}).get("home")
        aws = match.get("goals", {}).get("away")
        hs = 0 if hs is None else hs
        aws = 0 if aws is None else aws
        score = f"{hs} : {aws}"

        draw.rounded_rectangle(
            (492, y+28, 588, y+90),
            14,
            fill=(8, 57, 83, 255),
            outline=(55, 160, 215, 230),
            width=2
        )

        box = draw.textbbox(
            (0, 0), score, font=font(28, True)
        )
        w = box[2] - box[0]

        draw.text(
            (540-w/2, y+41),
            score,
            font=font(28, True),
            fill=(255, 255, 255, 255)
        )

    elif state == "live":
        hs = match.get("goals", {}).get("home") or 0
        aws = match.get("goals", {}).get("away") or 0
        minute = (
            match.get("fixture", {})
            .get("status", {})
            .get("elapsed")
        )

        draw.rounded_rectangle(
            (470, y+19, 610, y+98),
            16,
            fill=(135, 28, 38, 250),
            outline=(245, 75, 80, 240),
            width=2
        )

        draw.text(
            (495, y+25),
            f"LIVE {minute or ''}'",
            font=font(18, True),
            fill=(255, 255, 255, 255)
        )

        draw.text(
            (507, y+54),
            f"{hs} : {aws}",
            font=font(27, True),
            fill=(255, 255, 255, 255)
        )

    else:
        draw.rounded_rectangle(
            (493, y+31, 587, y+87),
            14,
            fill=(8, 43, 64, 255),
            outline=(43, 128, 175, 210),
            width=2
        )

        draw.text(
            (516, y+44),
            "VS",
            font=font(21, True),
            fill=(110, 210, 250, 255)
        )


def group_by_league(matches):
    groups = []

    for match in matches:
        league = match.get("league_name", "FUTBOL")

        if not groups or groups[-1][0] != league:
            groups.append((league, []))

        groups[-1][1].append(match)

    return groups


def make_pages(groups):
    pages = []
    current = []
    count = 0

    for league, matches in groups:
        for match in matches:
            if count >= MAX_MATCHES_PER_IMAGE:
                pages.append(current)
                current = []
                count = 0

            # Agar liga sahifada allaqachon bo'lsa, unga qo'shamiz.
            found = False
            for i, (lname, items) in enumerate(current):
                if lname == league:
                    items.append(match)
                    found = True
                    break

            if not found:
                current.append((league, [match]))

            count += 1

    if current:
        pages.append(current)

    return pages or [[]]


def make_image(title, date_string, page_groups, page_no, total_pages):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d")

    match_count = sum(
        len(items) for _, items in page_groups
    )
    league_count = len(page_groups)

    # Muhim: balandlik endi hech qachon kesilmaydi.
    height = (
        430
        + league_count * 95
        + match_count * 138
        + 145
    )

    image = Image.new(
        "RGBA",
        (IMAGE_WIDTH, height),
        (5, 16, 29, 255)
    )
    draw = ImageDraw.Draw(image, "RGBA")

    # Background
    for yy in range(height):
        ratio = yy / max(1, height-1)
        draw.line(
            (0, yy, IMAGE_WIDTH, yy),
            fill=(
                int(5 + 3*ratio),
                int(17 + 10*ratio),
                int(30 + 18*ratio),
                255
            )
        )

    # Diagonal design
    for x in range(-300, IMAGE_WIDTH+400, 190):
        draw.polygon(
            [
                (x, 0),
                (x+65, 0),
                (x-170, 245),
                (x-235, 245)
            ],
            fill=(25, 125, 190, 28)
        )

    # Header logo
    draw.ellipse(
        (55, 45, 160, 150),
        fill=(10, 72, 112, 100),
        outline=(70, 185, 240, 230),
        width=3
    )

    draw.text(
        (87, 65),
        "F",
        font=font(52, True),
        fill=(255, 255, 255, 255)
    )

    draw.text(
        (190, 55),
        "FUTBOL OLAMI",
        font=font(52, True),
        fill=(245, 250, 255, 255)
    )

    draw.text(
        (193, 116),
        "Futbol haqida hammasi!",
        font=font(23),
        fill=(130, 205, 245, 255)
    )

    # Date card
    draw.rounded_rectangle(
        (55, 185, 205, 325),
        20,
        fill=(245, 249, 252, 255)
    )
    draw.rounded_rectangle(
        (55, 185, 205, 230),
        20,
        fill=(235, 55, 55, 255)
    )
    draw.rectangle(
        (55, 210, 205, 230),
        fill=(235, 55, 55, 255)
    )

    months = {
        1:"YANVAR",2:"FEVRAL",3:"MART",4:"APREL",
        5:"MAY",6:"IYUN",7:"IYUL",8:"AVGUST",
        9:"SENTABR",10:"OKTABR",11:"NOYABR",12:"DEKABR"
    }

    draw.text(
        (78, 191),
        months[date_obj.month],
        font=font(18, True),
        fill=(255,255,255,255)
    )

    draw.text(
        (88, 235),
        date_obj.strftime("%d"),
        font=font(60, True),
        fill=(8,25,40,255)
    )

    draw.text(
        (245, 190),
        title,
        font=font(39, True),
        fill=(248,252,255,255)
    )

    days = {
        0:"DUSHANBA",1:"SESHANBA",2:"CHORSHANBA",
        3:"PAYSHANBA",4:"JUMA",5:"SHANBA",6:"YAKSHANBA"
    }

    draw.text(
        (248, 250),
        f"{date_obj.strftime('%d.%m.%Y')} | {days[date_obj.weekday()]}",
        font=font(22),
        fill=(145,200,230,255)
    )

    if total_pages > 1:
        draw.rounded_rectangle(
            (900, 195, 1015, 250),
            16,
            fill=(7,105,155,235)
        )
        draw.text(
            (926, 207),
            f"{page_no}/{total_pages}",
            font=font(21, True),
            fill=(255,255,255,255)
        )

    # Matches
    y = 355

    for league, matches in page_groups:
        draw.rounded_rectangle(
            (55, y, IMAGE_WIDTH-55, y+70),
            18,
            fill=(7, 39, 62, 255),
            outline=(45, 140, 195, 230),
            width=2
        )

        draw.text(
            (78, y+20),
            league,
            font=font(25, True),
            fill=(248,252,255,255)
        )

        y += 88

        for match in matches:
            draw_match(image, y, match)
            y += 138

        y += 12

    # Footer pastdagi joyga chiqadi
    footer_y = height - 145

    draw.line(
        (65, footer_y, IMAGE_WIDTH-65, footer_y),
        fill=(55, 135, 175, 150),
        width=2
    )

    draw.text(
        (75, footer_y+25),
        "Futbol bizni birlashtiradi!",
        font=font(28, True),
        fill=(238,248,255,255)
    )

    draw.text(
        (75, footer_y+73),
        "Futbol olami  •  Futbol haqida hammasi!",
        font=font(20),
        fill=(125,195,225,255)
    )

    return image.convert("RGB")


def send_photo(image, caption):
    buffer = BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=92,
        optimize=True
    )
    buffer.seek(0)

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": CHANNEL_ID,
            "caption": caption,
            "parse_mode": "HTML"
        },
        files={
            "photo": (
                "futbol-olami.jpg",
                buffer,
                "image/jpeg"
            )
        },
        timeout=30
    )

    result = response.json()

    if not result.get("ok"):
        raise Exception(str(result))

    return result


def publish_day(date_string, title):
    matches = get_matches(date_string)
    groups = group_by_league(matches)
    pages = make_pages(groups)

    total = len(pages)

    for page_no, page_groups in enumerate(pages, 1):
        image = make_image(
            title,
            date_string,
            page_groups,
            page_no,
            total
        )

        caption = (
            f"<b>FUTBOL OLAMI</b>\n"
            f"{title}\n"
            f"{date_string[8:10]}."
            f"{date_string[5:7]}."
            f"{date_string[0:4]}"
        )

        if total > 1:
            caption += f"\nSahifa: {page_no}/{total}"

        send_photo(image, caption)


def run_bot():
    now = datetime.now(TASHKENT)
    today = now.date()
    yesterday = today - timedelta(days=1)

    publish_day(
        yesterday.strftime("%Y-%m-%d"),
        "KECHAGI O‘YINLAR NATIJALARI"
    )

    publish_day(
        today.strftime("%Y-%m-%d"),
        "BUGUNGI O‘YINLAR"
    )


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        authorization = self.headers.get(
            "authorization",
            ""
        )

        if (
            not CRON_SECRET
            or authorization != f"Bearer {CRON_SECRET}"
        ):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        try:
            run_bot()

            result = {
                "ok": True,
                "message": "Futbol olami cron completed"
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

        except Exception as error:
            print("CRON ERROR:", error)

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
                        "error": str(error)
                    },
                    ensure_ascii=False
                ).encode("utf-8")
            )
