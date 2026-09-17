import os
import json
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler

from PIL import Image, ImageDraw, ImageFont


# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io"

TASHKENT = ZoneInfo("Asia/Tashkent")

IMAGE_WIDTH = 1080
MIN_IMAGE_HEIGHT = 1150
MAX_IMAGE_HEIGHT = 1800

# Bitta rasmga maksimal o'yinlar soni
MAX_MATCHES_PER_IMAGE = 7


# =========================================================
# SHRIFlAR
# =========================================================

FONT_DIR = os.path.join(
    os.path.dirname(__file__),
    "fonts"
)

FONT_REGULAR = os.path.join(
    FONT_DIR,
    "DejaVuSans.ttf"
)

FONT_BOLD = os.path.join(
    FONT_DIR,
    "DejaVuSans-Bold.ttf"
)


def get_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(path, size)


# =========================================================
# LIGALAR
# =========================================================

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


# =========================================================
# API
# =========================================================

def api_get(endpoint, params):
    headers = {
        "x-apisports-key": API_KEY,
        "Accept": "application/json"
    }

    response = requests.get(
        f"{API_URL}/{endpoint}",
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise Exception(
            str(data["errors"])
        )

    return data.get("response", [])


# =========================================================
# O'YINLARNI OLISH
# =========================================================

def get_fixtures(date_string):
    return api_get(
        "fixtures",
        {
            "date": date_string,
            "timezone": "Asia/Tashkent"
        }
    )


def get_selected_fixtures(date_string):

    fixtures = get_fixtures(date_string)

    result = []

    for match in fixtures:

        league = match.get(
            "league",
            {}
        )

        league_id = league.get("id")
        country = league.get(
            "country",
            ""
        )

        # Tanlangan asosiy ligalar
        if league_id in LEAGUE_IDS:

            match["league_name"] = (
                LEAGUE_IDS[league_id]
            )

            result.append(match)

        # O'zbekistonning barcha ligalari
        elif country == "Uzbekistan":

            league_name = league.get(
                "name",
                "FUTBOL"
            )

            match["league_name"] = (
                "O‘ZBEKISTON — "
                + league_name
            )

            result.append(match)

    # Avval liga, keyin vaqt
    result.sort(
        key=lambda x: (
            x.get(
                "league_name",
                ""
            ),
            x.get(
                "fixture",
                {}
            ).get(
                "date",
                ""
            )
        )
    )

    return result


# =========================================================
# LOGOTIPLAR
# =========================================================

logo_cache = {}


def get_logo(url):

    if not url:
        return None

    if url in logo_cache:
        return logo_cache[url]

    try:

        response = requests.get(
            url,
            timeout=10
        )

        response.raise_for_status()

        logo = Image.open(
            BytesIO(
                response.content
            )
        ).convert("RGBA")

        logo.thumbnail(
            (70, 70),
            Image.Resampling.LANCZOS
        )

        logo_cache[url] = logo

        return logo

    except Exception as error:

        print(
            f"LOGO ERROR: {error}"
        )

        logo_cache[url] = None

        return None


def draw_logo(
    image,
    logo_url,
    center_x,
    center_y,
    size=64
):

    draw = ImageDraw.Draw(
        image,
        "RGBA"
    )

    # Logo uchun fon
    draw.ellipse(
        (
            center_x - size // 2,
            center_y - size // 2,
            center_x + size // 2,
            center_y + size // 2
        ),
        fill=(7, 31, 49, 255),
        outline=(45, 140, 195, 220),
        width=2
    )

    logo = get_logo(
        logo_url
    )

    if logo:

        copy = logo.copy()

        copy.thumbnail(
            (
                size - 12,
                size - 12
            ),
            Image.Resampling.LANCZOS
        )

        x = int(
            center_x
            - copy.width / 2
        )

        y = int(
            center_y
            - copy.height / 2
        )

        # MUHIM:
        # alpha_composite Image obyektida ishlaydi
        image.alpha_composite(
            copy,
            (x, y)
        )


# =========================================================
# O'YIN STATUSI
# =========================================================

def get_match_status(match):

    status = (
        match
        .get("fixture", {})
        .get("status", {})
        .get("short", "")
    )

    if status in [
        "FT",
        "AET",
        "P"
    ]:
        return "finished"

    if status in [
        "1H",
        "2H",
        "HT",
        "ET",
        "BT"
    ]:
        return "live"

    return "upcoming"


def get_match_time(match):

    date_value = (
        match
        .get("fixture", {})
        .get("date", "")
    )

    if len(date_value) >= 16:
        return date_value[11:16]

    return "--:--"


# =========================================================
# NOMLARNI QISQARTIRISH
# =========================================================

def team_name_for_display(name):

    replacements = {
        "Manchester United": "Man United",
        "Manchester City": "Man City",
        "Tottenham Hotspur": "Tottenham",
        "Wolverhampton Wanderers": "Wolves",
        "Brighton Hove Albion": "Brighton",
        "West Ham United": "West Ham",
        "Newcastle United": "Newcastle",
        "Nottingham Forest": "Nott'm Forest",
        "Crystal Palace": "Crystal Palace",
        "Real Sociedad": "Real Sociedad",
        "Rayo Vallecano": "Rayo Vallecano",
        "Athletic Club": "Athletic",
        "Racing Santander": "Racing",
        "Paris Saint Germain": "PSG",
        "Inter": "Inter",
        "Bayern Munich": "Bayern",
    }

    return replacements.get(
        name,
        name
    )


def fit_team_font(name):

    length = len(name)

    if length > 23:
        return get_font(
            18,
            True
        )

    if length > 18:
        return get_font(
            20,
            True
        )

    return get_font(
        22,
        True
    )


# =========================================================
# O'YIN QATORI
# =========================================================

def draw_match(
    image,
    y,
    match
):

    draw = ImageDraw.Draw(
        image,
        "RGBA"
    )

    home = (
        match
        .get("teams", {})
        .get("home", {})
    )

    away = (
        match
        .get("teams", {})
        .get("away", {})
    )

    home_name = team_name_for_display(
        home.get(
            "name",
            "?"
        )
    )

    away_name = team_name_for_display(
        away.get(
            "name",
            "?"
        )
    )

    # Qator
    draw.rounded_rectangle(
        (
            50,
            y,
            IMAGE_WIDTH - 50,
            y + 105
        ),
        18,
        fill=(5, 24, 41, 245),
        outline=(35, 110, 155, 190),
        width=2
    )

    # Vaqt
    draw.text(
        (
            72,
            y + 39
        ),
        get_match_time(match),
        font=get_font(
            24,
            True
        ),
        fill=(235, 245, 252, 255)
    )

    # Logotiplar
    draw_logo(
        image,
        home.get("logo"),
        420,
        y + 52,
        62
    )

    draw_logo(
        image,
        away.get("logo"),
        660,
        y + 52,
        62
    )

    # Jamoa nomlari
    home_font = fit_team_font(
        home_name
    )

    away_font = fit_team_font(
        away_name
    )

    home_box = draw.textbbox(
        (0, 0),
        home_name,
        font=home_font
    )

    away_box = draw.textbbox(
        (0, 0),
        away_name,
        font=away_font
    )

    home_width = (
        home_box[2]
        - home_box[0]
    )

    away_width = (
        away_box[2]
        - away_box[0]
    )

    # Home nomi o'ngga tekislanadi
    draw.text(
        (
            400 - home_width,
            y + 42
        ),
        home_name,
        font=home_font,
        fill=(248, 251, 255, 255)
    )

    # Away nomi chapga tekislanadi
    draw.text(
        (
            685,
            y + 42
        ),
        away_name,
        font=away_font,
        fill=(248, 251, 255, 255)
    )

    status = get_match_status(
        match
    )

    # =====================================================
    # YAKUNLANGAN
    # =====================================================

    if status == "finished":

        home_score = (
            match
            .get("goals", {})
            .get("home")
        )

        away_score = (
            match
            .get("goals", {})
            .get("away")
        )

        if home_score is None:
            home_score = 0

        if away_score is None:
            away_score = 0

        score = (
            f"{home_score} : "
            f"{away_score}"
        )

        draw.rounded_rectangle(
            (
                485,
                y + 24,
                595,
                y + 82
            ),
            12,
            fill=(7, 48, 72, 255),
            outline=(50, 155, 210, 230),
            width=2
        )

        box = draw.textbbox(
            (0, 0),
            score,
            font=get_font(
                27,
                True
            )
        )

        score_width = (
            box[2]
            - box[0]
        )

        draw.text(
            (
                540
                - score_width / 2,
                y + 35
            ),
            score,
            font=get_font(
                27,
                True
            ),
            fill=(255, 255, 255, 255)
        )

    # =====================================================
    # LIVE
    # =====================================================

    elif status == "live":

        home_score = (
            match
            .get("goals", {})
            .get("home")
            or 0
        )

        away_score = (
            match
            .get("goals", {})
            .get("away")
            or 0
        )

        minute = (
            match
            .get("fixture", {})
            .get("status", {})
            .get("elapsed")
        )

        if minute:
            live_text = (
                f"LIVE {minute}'"
            )
        else:
            live_text = "LIVE"

        draw.rounded_rectangle(
            (
                460,
                y + 17,
                620,
                y + 88
            ),
            15,
            fill=(135, 24, 35, 245),
            outline=(245, 70, 75, 240),
            width=2
        )

        draw.text(
            (
                475,
                y + 23
            ),
            live_text,
            font=get_font(
                17,
                True
            ),
            fill=(255, 255, 255, 255)
        )

        score = (
            f"{home_score} : "
            f"{away_score}"
        )

        draw.text(
            (
                505,
                y + 49
            ),
            score,
            font=get_font(
                25,
                True
            ),
            fill=(255, 255, 255, 255)
        )

    # =====================================================
    # KELAJAKDAGI O'YIN
    # =====================================================

    else:

        draw.rounded_rectangle(
            (
                490,
                y + 27,
                590,
                y + 78
            ),
            12,
            fill=(8, 38, 58, 255),
            outline=(40, 120, 165, 180),
            width=2
        )

        draw.text(
            (
                515,
                y + 40
            ),
            "VS",
            font=get_font(
                20,
                True
            ),
            fill=(100, 205, 250, 255)
        )


# =========================================================
# LIGA SARLAVHASI
# =========================================================

def draw_league_header(
    image,
    y,
    league_name
):

    draw = ImageDraw.Draw(
        image,
        "RGBA"
    )

    draw.rounded_rectangle(
        (
            50,
            y,
            IMAGE_WIDTH - 50,
            y + 72
        ),
        18,
        fill=(7, 38, 61, 255),
        outline=(40, 135, 190, 230),
        width=2
    )

    draw.text(
        (
            75,
            y + 21
        ),
        league_name,
        font=get_font(
            25,
            True
        ),
        fill=(248, 252, 255, 255)
    )

    return y + 88


# =========================================================
# LIGALAR BO'YICHA GURUHLASH
# =========================================================

def group_by_league(matches):

    groups = []

    current_league = None

    for match in matches:

        league = match.get(
            "league_name",
            "FUTBOL"
        )

        if league != current_league:

            groups.append(
                (
                    league,
                    []
                )
            )

            current_league = league

        groups[-1][1].append(
            match
        )

    return groups


# =========================================================
# RASMLARGA BO'LISH
# =========================================================

def split_into_pages(
    groups
):

    pages = []

    current_page = []
    current_count = 0

    for league, matches in groups:

        start = 0

        while start < len(matches):

            remaining = (
                MAX_MATCHES_PER_IMAGE
                - current_count
            )

            if remaining <= 0:

                pages.append(
                    current_page
                )

                current_page = []
                current_count = 0

                remaining = (
                    MAX_MATCHES_PER_IMAGE
                )

            chunk = matches[
                start:
                start + remaining
            ]

            current_page.append(
                (
                    league,
                    chunk
                )
            )

            current_count += len(
                chunk
            )

            start += len(chunk)

            if current_count >= MAX_MATCHES_PER_IMAGE:

                pages.append(
                    current_page
                )

                current_page = []
                current_count = 0

    if current_page:
        pages.append(
            current_page
        )

    if not pages:
        pages = [[]]

    return pages


# =========================================================
# KUN NOMLARI
# =========================================================

DAY_NAMES = {
    0: "DUSHANBA",
    1: "SESHANBA",
    2: "CHORSHANBA",
    3: "PAYSHANBA",
    4: "JUMA",
    5: "SHANBA",
    6: "YAKSHANBA"
}


# =========================================================
# RASM YARATISH
# =========================================================

def build_image(
    title,
    date_string,
    page_groups,
    page_number,
    total_pages
):

    date_object = datetime.strptime(
        date_string,
        "%Y-%m-%d"
    )

    date_display = date_object.strftime(
        "%d.%m.%Y"
    )

    # Qatorlar soni
    match_count = sum(
        len(matches)
        for _, matches
        in page_groups
    )

    league_count = len(
        page_groups
    )

    # Dinamik balandlik
    height = (
        400
        + match_count * 115
        + league_count * 100
    )

    height = max(
        MIN_IMAGE_HEIGHT,
        min(
            MAX_IMAGE_HEIGHT,
            height
        )
    )

    # =====================================================
    # ASOSIY RASM
    # =====================================================

    image = Image.new(
        "RGBA",
        (
            IMAGE_WIDTH,
            height
        ),
        (
            4,
            14,
            27,
            255
        )
    )

    draw = ImageDraw.Draw(
        image,
        "RGBA"
    )

    # =====================================================
    # FON GRADIENT
    # =====================================================

    for y in range(height):

        ratio = (
            y
            / max(
                1,
                height - 1
            )
        )

        r = int(
            4 + 4 * ratio
        )

        g = int(
            15 + 13 * ratio
        )

        b = int(
            29 + 23 * ratio
        )

        draw.line(
            (
                0,
                y,
                IMAGE_WIDTH,
                y
            ),
            fill=(
                r,
                g,
                b,
                255
            )
        )

    # Dekorativ chiziqlar
    for x in range(
        -300,
        IMAGE_WIDTH + 400,
        180
    ):

        draw.polygon(
            [
                (x, 0),
                (x + 65, 0),
                (x - 180, 260),
                (x - 245, 260)
            ],
            fill=(
                20,
                100,
                155,
                22
            )
        )

    # =====================================================
    # LOGO
    # =====================================================

    draw.ellipse(
        (
            55,
            42,
            160,
            147
        ),
        fill=(
            10,
            75,
            115,
            80
        ),
        outline=(
            60,
            180,
            240,
            220
        ),
        width=3
    )

    draw.text(
        (
            82,
            65
        ),
        "F",
        font=get_font(
            52,
            True
        ),
        fill=(
            255,
            255,
            255,
            255
        )
    )

    draw.text(
        (
            190,
            55
        ),
        "FUTBOL OLAMI",
        font=get_font(
            52,
            True
        ),
        fill=(
            245,
            250,
            255,
            255
        )
    )

    draw.text(
        (
            193,
            116
        ),
        "Futbol haqida hammasi!",
        font=get_font(
            22,
            False
        ),
        fill=(
            130,
            205,
            245,
            255
        )
    )

    # =====================================================
    # SANA
    # =====================================================

    draw.rounded_rectangle(
        (
            55,
            185,
            205,
            325
        ),
        20,
        fill=(
            245,
            249,
            252,
            255
        )
    )

    draw.rounded_rectangle(
        (
            55,
            185,
            205,
            228
        ),
        20,
        fill=(
            235,
            55,
            55,
            255
        )
    )

    draw.rectangle(
        (
            55,
            210,
            205,
            228
        ),
        fill=(
            235,
            55,
            55,
            255
        )
    )

    month_names = {
        1: "YANVAR",
        2: "FEVRAL",
        3: "MART",
        4: "APREL",
        5: "MAY",
        6: "IYUN",
        7: "IYUL",
        8: "AVGUST",
        9: "SENTABR",
        10: "OKTABR",
        11: "NOYABR",
        12: "DEKABR"
    }

    draw.text(
        (
            78,
            190
        ),
        month_names[
            date_object.month
        ],
        font=get_font(
            18,
            True
        ),
        fill=(
            255,
            255,
            255,
            255
        )
    )

    draw.text(
        (
            88,
            235
        ),
        date_object.strftime(
            "%d"
        ),
        font=get_font(
            60,
            True
        ),
        fill=(
            8,
            25,
            40,
            255
        )
    )

    # =====================================================
    # SARLAVHA
    # =====================================================

    draw.text(
        (
            245,
            190
        ),
        title,
        font=get_font(
            39,
            True
        ),
        fill=(
            248,
            252,
            255,
            255
        )
    )

    draw.text(
        (
            248,
            250
        ),
        (
            f"{date_display} | "
            f"{DAY_NAMES[date_object.weekday()]}"
        ),
        font=get_font(
            22,
            False
        ),
        fill=(
            145,
            200,
            230,
            255
        )
    )

    # Sahifa
    if total_pages > 1:

        page_text = (
            f"{page_number}/{total_pages}"
        )

        draw.rounded_rectangle(
            (
                900,
                195,
                1015,
                250
            ),
            16,
            fill=(
                7,
                105,
                155,
                230
            )
        )

        draw.text(
            (
                925,
                207
            ),
            page_text,
            font=get_font(
                21,
                True
            ),
            fill=(
                255,
                255,
                255,
                255
            )
        )

    # =====================================================
    # LIGALAR VA O'YINLAR
    # =====================================================

    y = 355

    for league, matches in page_groups:

        y = draw_league_header(
            image,
            y,
            league
        )

        for match in matches:

            draw_match(
                image,
                y,
                match
            )

            y += 115

        y += 10

    # =====================================================
    # FOOTER
    # =====================================================

    footer_y = height - 145

    draw.line(
        (
            60,
            footer_y,
            IMAGE_WIDTH - 60,
            footer_y
        ),
        fill=(
            45,
            125,
            165,
            130
        ),
        width=2
    )

    draw.text(
        (
            70,
            footer_y + 25
        ),
        "Futbol bizni birlashtiradi!",
        font=get_font(
            28,
            True
        ),
        fill=(
            235,
            248,
            255,
            255
        )
    )

    draw.text(
        (
            70,
            footer_y + 72
        ),
        "Futbol olami  •  Futbol haqida hammasi!",
        font=get_font(
            20,
            False
        ),
        fill=(
            120,
            195,
            230,
            255
        )
    )

    return image.convert(
        "RGB"
    )


# =========================================================
# TELEGRAMGA RASM YUBORISH
# =========================================================

def send_photo(
    image,
    caption
):

    buffer = BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=92,
        optimize=True
    )

    buffer.seek(0)

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto"
    )

    response = requests.post(
        url,
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
        raise Exception(
            str(result)
        )

    return result


# =========================================================
# KUNNI E'LON QILISH
# =========================================================

def publish_day(
    date_string,
    title
):

    matches = get_selected_fixtures(
        date_string
    )

    groups = group_by_league(
        matches
    )

    pages = split_into_pages(
        groups
    )

    total_pages = len(
        pages
    )

    for index, page_groups in enumerate(
        pages,
        start=1
    ):

        image = build_image(
            title,
            date_string,
            page_groups,
            index,
            total_pages
        )

        caption = (
            f"<b>FUTBOL OLAMI</b>\n"
            f"{title}\n"
            f"{date_string[8:10]}."
            f"{date_string[5:7]}."
            f"{date_string[0:4]}"
        )

        if total_pages > 1:

            caption += (
                f"\nSahifa: "
                f"{index}/{total_pages}"
            )

        send_photo(
            image,
            caption
        )


# =========================================================
# ASOSIY ISH
# =========================================================

def run_bot():

    now = datetime.now(
        TASHKENT
    )

    today = now.date()

    yesterday = (
        today
        - timedelta(days=1)
    )

    # Kechagi natijalar
    publish_day(
        yesterday.strftime(
            "%Y-%m-%d"
        ),
        "KECHAGI O‘YINLAR NATIJALARI"
    )

    # Bugungi o'yinlar
    publish_day(
        today.strftime(
            "%Y-%m-%d"
        ),
        "BUGUNGI O‘YINLAR"
    )


# =========================================================
# VERCEL CRON
# =========================================================

class handler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        authorization = self.headers.get(
            "authorization",
            ""
        )

        expected = (
            f"Bearer {CRON_SECRET}"
        )

        # Cron himoyasi
        if (
            not CRON_SECRET
            or authorization != expected
        ):

            self.send_response(
                401
            )

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
                "message": (
                    "Futbol olami "
                    "image cron completed"
                )
            }

            self.send_response(
                200
            )

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

            print(
                f"CRON ERROR: {error}"
            )

            self.send_response(
                500
            )

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
