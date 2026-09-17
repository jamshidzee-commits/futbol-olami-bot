import os
import json
import html
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler

from PIL import Image, ImageDraw, ImageFont, ImageOps

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io"
TASHKENT = ZoneInfo("Asia/Tashkent")

LEAGUE_IDS = {
    39: "ANGLIYA — PREMIER LEAGUE",
    140: "ISPANIYA — LA LIGA",
    135: "ITALIYA — SERIE A",
    78: "GERMANIYA — BUNDESLIGA",
    61: "FRANSIYA — LIGUE 1",
    2: "CHEMPIONLAR LIGASI",
    3: "YEVROPA LIGASI",
    848: "KONFERENSIYALAR LIGASI",
}

# Har bir rasmda ko‘p qator bo‘lib ketmasligi uchun.
MAX_MATCHES_PER_IMAGE = 7
IMAGE_WIDTH = 1080
MIN_HEIGHT = 1150
MAX_HEIGHT = 1700

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

_logo_cache = {}


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


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
                "O‘ZBEKISTON — " + league.get("name", "FUTBOL")
            )
            result.append(match)

    result.sort(
        key=lambda x: (
            x.get("league_name", ""),
            x.get("fixture", {}).get("date", ""),
        )
    )
    return result


def get_logo(url):
    if not url:
        return None

    if url in _logo_cache:
        return _logo_cache[url]

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        image = Image.open(BytesIO(response.content)).convert("RGBA")
        image.thumbnail((72, 72), Image.Resampling.LANCZOS)

        _logo_cache[url] = image
        return image
    except Exception as e:
        print(f"Logo error: {e}")
        _logo_cache[url] = None
        return None


def draw_logo(image, logo_url, center_x, center_y, size=58):
    draw = ImageDraw.Draw(image, "RGBA")

    draw.ellipse(
        (
            center_x - size // 2,
            center_y - size // 2,
            center_x + size // 2,
            center_y + size // 2,
        ),
        fill=(8, 29, 47, 255),
        outline=(40, 125, 175, 220),
        width=2,
    )

    logo = get_logo(logo_url)
    if logo:
        copy = logo.copy()
        copy.thumbnail((size - 10, size - 10), Image.Resampling.LANCZOS)
        x = center_x - copy.width // 2
        y = center_y - copy.height // 2
        image.alpha_composite(copy, (x, y))


def fixture_status(match):
    status = match.get("fixture", {}).get("status", {}).get("short", "")

    if status in ["FT", "AET", "P"]:
        return "finished"

    if status in ["1H", "2H", "HT", "ET", "BT", "P"]:
        return "live"

    return "upcoming"


def match_time(match):
    value = match.get("fixture", {}).get("date", "")
    return value[11:16] if len(value) >= 16 else "--:--"


def draw_match(canvas_image, y, match):
    canvas = ImageDraw.Draw(canvas_image, "RGBA")
    home = match.get("teams", {}).get("home", {})
    away = match.get("teams", {}).get("away", {})

    home_name = home.get("name", "?")
    away_name = away.get("name", "?")

    # Qator
    canvas.rounded_rectangle(
        (50, y, IMAGE_WIDTH - 50, y + 105),
        18,
        fill=(5, 24, 41, 235),
        outline=(34, 104, 145, 180),
        width=2,
    )

    time = match_time(match)
    status = fixture_status(match)

    canvas.text(
        (75, y + 39),
        time,
        font=font(25, True),
        fill=(230, 242, 250, 255),
    )

    # Home
    home_logo_url = home.get("logo")
    away_logo_url = away.get("logo")

    draw_logo(canvas_image, home_logo_url, 385, y + 52, 60)
    draw_logo(canvas_image, away_logo_url, 695, y + 52, 60)

    # Team nomlarini markazga yaqin joylashtiramiz
    home_font = font(22, True)
    away_font = font(22, True)

    hb = canvas.textbbox((0, 0), home_name, font=home_font)
    ab = canvas.textbbox((0, 0), away_name, font=away_font)

    home_w = hb[2] - hb[0]
    away_w = ab[2] - ab[0]

    canvas.text(
        (340 - home_w, y + 42),
        home_name,
        font=home_font,
        fill=(245, 250, 255, 255),
    )

    canvas.text(
        (735, y + 42),
        away_name,
        font=away_font,
        fill=(245, 250, 255, 255),
    )

    if status == "finished":
        hs = match.get("goals", {}).get("home")
        aws = match.get("goals", {}).get("away")
        hs = 0 if hs is None else hs
        aws = 0 if aws is None else aws

        score = f"{hs} : {aws}"

        canvas.rounded_rectangle(
            (485, y + 25, 595, y + 80),
            12,
            fill=(7, 48, 72, 255),
            outline=(54, 155, 210, 230),
            width=2,
        )

        sb = canvas.textbbox((0, 0), score, font=font(27, True))
        canvas.text(
            (540 - (sb[2] - sb[0]) / 2, y + 35),
            score,
            font=font(27, True),
            fill=(255, 255, 255, 255),
        )

    elif status == "live":
        hs = match.get("goals", {}).get("home") or 0
        aws = match.get("goals", {}).get("away") or 0
        minute = match.get("fixture", {}).get("status", {}).get("elapsed")

        score = f"{hs} : {aws}"
        label = f"LIVE {minute or ''}'"

        canvas.rounded_rectangle(
            (460, y + 17, 620, y + 88),
            15,
            fill=(135, 24, 35, 245),
            outline=(240, 65, 70, 240),
            width=2,
        )

        canvas.text(
            (477, y + 24),
            label,
            font=font(18, True),
            fill=(255, 255, 255, 255),
        )
        canvas.text(
            (510, y + 50),
            score,
            font=font(25, True),
            fill=(255, 255, 255, 255),
        )

    else:
        canvas.rounded_rectangle(
            (485, y + 28, 595, y + 78),
            12,
            fill=(8, 38, 58, 255),
            outline=(40, 120, 165, 180),
            width=2,
        )

        vs = "VS"
        vb = canvas.textbbox((0, 0), vs, font=font(21, True))
        canvas.text(
            (540 - (vb[2] - vb[0]) / 2, y + 39),
            vs,
            font=font(21, True),
            fill=(105, 205, 250, 255),
        )


def league_header(canvas, y, name):
    canvas.rounded_rectangle(
        (50, y, IMAGE_WIDTH - 50, y + 72),
        18,
        fill=(7, 38, 61, 255),
        outline=(40, 135, 190, 230),
        width=2,
    )

    canvas.text(
        (75, y + 20),
        name,
        font=font(26, True),
        fill=(248, 252, 255, 255),
    )

    return y + 86


def group_matches(matches):
    groups = []
    current = None

    for match in matches:
        league = match.get("league_name", "FUTBOL")

        if league != current:
            groups.append((league, []))
            current = league

        groups[-1][1].append(match)

    return groups


def split_groups(groups):
    pages = []
    current = []
    count = 0

    for league, matches in groups:
        if current and count + len(matches) > MAX_MATCHES_PER_IMAGE:
            pages.append(current)
            current = []
            count = 0

        # Agar bitta liga o‘zi juda katta bo‘lsa, uni ham bo‘lib yuboramiz.
        for i in range(0, len(matches), MAX_MATCHES_PER_IMAGE):
            chunk = matches[i:i + MAX_MATCHES_PER_IMAGE]

            if current and count + len(chunk) > MAX_MATCHES_PER_IMAGE:
                pages.append(current)
                current = []
                count = 0

            current.append((league, chunk))
            count += len(chunk)

            if count >= MAX_MATCHES_PER_IMAGE:
                pages.append(current)
                current = []
                count = 0

    if current:
        pages.append(current)

    return pages


def build_image(title, date_string, page_groups, page_number, total_pages):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d")
    date_display = date_obj.strftime("%d.%m.%Y")

    # Dinamik balandlik
    rows = sum(len(matches) for _, matches in page_groups)
    headers = len(page_groups)

    height = 390 + rows * 115 + headers * 100
    height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))

    image = Image.new(
        "RGBA",
        (IMAGE_WIDTH, height),
        (4, 14, 27, 255),
    )

    canvas = ImageDraw.Draw(image, "RGBA")

    # Fon
    for y in range(height):
        ratio = y / max(1, height - 1)
        fill = (
            int(4 + 4 * ratio),
            int(15 + 13 * ratio),
            int(29 + 22 * ratio),
            255,
        )
        canvas.line((0, y, IMAGE_WIDTH, y), fill=fill)

    # Yuqori dekor
    for x in range(-200, IMAGE_WIDTH + 300, 180):
        canvas.polygon(
            [(x, 0), (x + 65, 0), (x - 180, 260), (x - 245, 260)],
            fill=(20, 100, 155, 25),
        )

    # Logo / title
    canvas.ellipse(
        (55, 42, 160, 147),
        fill=(10, 75, 115, 80),
        outline=(60, 180, 240, 220),
        width=3,
    )

    canvas.text(
        (82, 66),
        "⚽",
        font=font(48),
        fill=(255, 255, 255, 255),
    )

    canvas.text(
        (190, 55),
        "FUTBOL OLAMI",
        font=font(52, True),
        fill=(245, 250, 255, 255),
    )

    canvas.text(
        (193, 116),
        "Futbol haqida hammasi!",
        font=font(22, False),
        fill=(130, 205, 245, 255),
    )

    # Sana va sarlavha
    canvas.rounded_rectangle(
        (55, 185, 205, 325),
        20,
        fill=(245, 249, 252, 255),
    )
    canvas.rounded_rectangle(
        (55, 185, 205, 228),
        20,
        fill=(235, 55, 55, 255),
    )
    canvas.rectangle((55, 210, 205, 228), fill=(235, 55, 55, 255))

    canvas.text(
        (77, 190),
        date_obj.strftime("%B").upper(),
        font=font(19, True),
        fill=(255, 255, 255, 255),
    )

    canvas.text(
        (88, 235),
        date_obj.strftime("%d"),
        font=font(60, True),
        fill=(8, 25, 40, 255),
    )

    canvas.text(
        (245, 190),
        title,
        font=font(40, True),
        fill=(248, 252, 255, 255),
    )

    day_names = {
        0: "DUSHANBA",
        1: "SESHANBA",
        2: "CHORSHANBA",
        3: "PAYSHANBA",
        4: "JUMA",
        5: "SHANBA",
        6: "YAKSHANBA",
    }

    canvas.text(
        (248, 250),
        f"{date_display} | {day_names[date_obj.weekday()]}",
        font=font(22, False),
        fill=(145, 200, 230, 255),
    )

    if total_pages > 1:
        page = f"{page_number}/{total_pages}"
        canvas.rounded_rectangle(
            (900, 195, 1015, 250),
            16,
            fill=(7, 105, 155, 230),
        )
        canvas.text(
            (928, 208),
            page,
            font=font(21, True),
            fill=(255, 255, 255, 255),
        )

    y = 355

    for league, matches in page_groups:
        y = league_header(image_draw := canvas, y, league)

        for match in matches:
            draw_match(image, y, match)
            y += 115

        y += 10

    # Footer
    footer_y = height - 145
    canvas.line(
        (60, footer_y, IMAGE_WIDTH - 60, footer_y),
        fill=(45, 125, 165, 130),
        width=2,
    )

    canvas.text(
        (70, footer_y + 25),
        "Futbol bizni birlashtiradi!",
        font=font(28, True),
        fill=(235, 248, 255, 255),
    )

    canvas.text(
        (70, footer_y + 72),
        "Futbol olami  •  Futbol haqida hammasi!",
        font=font(21, False),
        fill=(120, 195, 230, 255),
    )

    return image.convert("RGB")


def send_photo(image, caption):
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={
            "photo": ("futbol-olami.jpg", buffer, "image/jpeg"),
        },
        timeout=30,
    )

    result = response.json()

    if not result.get("ok"):
        raise Exception(str(result))

    return result


def publish_day(date_string, title):
    matches = get_selected_fixtures(date_string)

    if not matches:
        # Rasm bo‘lib ham yuboramiz — kanal har kuni chiroyli ko‘rinadi.
        pages = [[]]
    else:
        pages = split_groups(group_matches(matches))

    total = len(pages)

    for index, page_groups in enumerate(pages, start=1):
        image = build_image(
            title,
            date_string,
            page_groups,
            index,
            total,
        )

        caption = (
            f"⚽ <b>FUTBOL OLAMI</b>\n"
            f"{html.escape(title)}\n"
            f"📅 {date_string[8:10]}.{date_string[5:7]}.{date_string[0:4]}"
        )

        if total > 1:
            caption += f"\n📄 {index}/{total}"

        send_photo(image, caption)


def run_bot():
    now = datetime.now(TASHKENT)
    today = now.date()
    yesterday = today - timedelta(days=1)

    publish_day(
        yesterday.strftime("%Y-%m-%d"),
        "KECHAGI O‘YINLAR NATIJALARI",
    )

    publish_day(
        today.strftime("%Y-%m-%d"),
        "BUGUNGI O‘YINLAR",
    )


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        authorization = self.headers.get("authorization", "")
        expected = f"Bearer {CRON_SECRET}"

        if not CRON_SECRET or authorization != expected:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        try:
            run_bot()

            result = {
                "ok": True,
                "message": "Futbol olami image cron completed",
            }

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                ).encode("utf-8")
            )

        except Exception as e:
            print(f"CRON ERROR: {e}")

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(e),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )
