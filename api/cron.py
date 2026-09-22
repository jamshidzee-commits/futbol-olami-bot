import os
import json
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler
from html.parser import HTMLParser
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_KEY = os.environ.get("FOOTBALL_API_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

API_URL = "https://v3.football.api-sports.io"
TASHKENT = ZoneInfo("Asia/Tashkent")

W = 1080
MAX_MATCHES = 5

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

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

# Turnir jadvallari uchun.
STANDINGS_LEAGUES = [
    (39, "ANGLIYA — PREMIER LIGA"),
    (140, "ISPANIYA — LA LIGA"),
    (135, "ITALIYA — SERIYA A"),
    (78, "GERMANIYA — BUNDESLIGA"),
    (61, "FRANSIYA — LIGUE 1"),
    (307, "SAUDIYA ARABIYASI — SAUDI PRO LEAGUE"),
    (94, "PORTUGALIYA — PRIMEIRA LIGA"),
    (88, "NIDERLANDIYA — EREDIVISIE"),
    (278, "O‘ZBEKISTON — SUPER LIGA"),
]

logo_cache = {}


def F(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


def api_get(endpoint, params):
    r = requests.get(
        f"{API_URL}/{endpoint}",
        headers={
            "x-apisports-key": API_KEY,
            "Accept": "application/json"
        },
        params=params,
        timeout=30
    )
    r.raise_for_status()
    data = r.json()

    if data.get("errors"):
        raise Exception(str(data["errors"]))

    return data.get("response", [])


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


def draw_logo(img, url, cx, cy, size=60):
    d = ImageDraw.Draw(img, "RGBA")

    d.ellipse(
        (cx-size//2, cy-size//2, cx+size//2, cy+size//2),
        fill=(7, 30, 47, 255),
        outline=(48, 145, 200, 220),
        width=2
    )

    logo = get_logo(url)

    if logo:
        p = logo.copy()
        p.thumbnail((size-10, size-10), Image.Resampling.LANCZOS)

        img.alpha_composite(
            p,
            (int(cx-p.width/2), int(cy-p.height/2))
        )


def current_season(date_obj, calendar_year=False):
    # API-Football seasons use the year in which a European season starts:
    # 2026/27 => season 2026.
    if calendar_year:
        return date_obj.year

    return date_obj.year if date_obj.month >= 7 else date_obj.year - 1


def get_matches(date_string):
    fixtures = api_get(
        "fixtures",
        {
            "date": date_string,
            "timezone": "Asia/Tashkent"
        }
    )

    result = []

    for m in fixtures:
        league = m.get("league", {})
        lid = league.get("id")

        if lid in LEAGUE_IDS:
            m["league_name"] = LEAGUE_IDS[lid]
            result.append(m)

        elif league.get("country") == "Uzbekistan":
            m["league_name"] = (
                "O‘ZBEKISTON — " +
                league.get("name", "FUTBOL").upper()
            )
            result.append(m)

    result.sort(
        key=lambda x: (
            x.get("league_name", ""),
            x.get("fixture", {}).get("date", "")
        )
    )

    return result


def status_of(m):
    s = (
        m.get("fixture", {})
        .get("status", {})
        .get("short", "")
    )

    if s in ("FT", "AET", "PEN"):
        return "finished"

    if s in ("1H", "2H", "HT", "ET", "BT", "P"):
        return "live"

    return "upcoming"


def time_of(m):
    v = m.get("fixture", {}).get("date", "")
    return v[11:16] if len(v) >= 16 else "--:--"


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
        "Deportivo La Coruna": "Deportivo",
    }

    return replacements.get(name, name)


def fit_text(d, text, max_width, start=24, minimum=16):
    text = short_name(text)

    for size in range(start, minimum - 1, -1):
        f = F(size, True)
        box = d.textbbox((0, 0), text, font=f)

        if box[2] - box[0] <= max_width:
            return text, f

    f = F(minimum, True)
    t = text

    while len(t) > 3:
        candidate = t[:-1] + "..."
        box = d.textbbox((0, 0), candidate, font=f)

        if box[2] - box[0] <= max_width:
            return candidate, f

        t = t[:-1]

    return t, f


def draw_match(img, y, m):
    d = ImageDraw.Draw(img, "RGBA")

    home = m.get("teams", {}).get("home", {})
    away = m.get("teams", {}).get("away", {})

    hn, hf = fit_text(d, home.get("name", "?"), 225)
    an, af = fit_text(d, away.get("name", "?"), 260)

    d.rounded_rectangle(
        (45, y, W-45, y+116),
        18,
        fill=(6, 27, 44, 250),
        outline=(38, 120, 165, 220),
        width=2
    )

    d.text(
        (70, y+43),
        time_of(m),
        font=F(25, True),
        fill=(240, 248, 252, 255)
    )

    hb = d.textbbox((0, 0), hn, font=hf)

    d.text(
        (405-(hb[2]-hb[0]), y+44),
        hn,
        font=hf,
        fill=(248, 251, 255, 255)
    )

    draw_logo(img, home.get("logo"), 440, y+58, 64)
    draw_logo(img, away.get("logo"), 640, y+58, 64)

    d.text(
        (680, y+44),
        an,
        font=af,
        fill=(248, 251, 255, 255)
    )

    state = status_of(m)

    if state == "finished":
        hs = m.get("goals", {}).get("home")
        aws = m.get("goals", {}).get("away")

        center = f"{0 if hs is None else hs} : {0 if aws is None else aws}"
        fill = (8, 58, 84, 255)
        outline = (55, 160, 215, 230)

    elif state == "live":
        hs = m.get("goals", {}).get("home") or 0
        aws = m.get("goals", {}).get("away") or 0

        minute = (
            m.get("fixture", {})
            .get("status", {})
            .get("elapsed")
        )

        center = f"{hs} : {aws}"
        fill = (130, 28, 38, 250)
        outline = (245, 75, 80, 240)

        d.text(
            (498, y+12),
            f"LIVE {minute or ''}'",
            font=F(15, True),
            fill=(255, 255, 255, 255)
        )

    else:
        center = "VS"
        fill = (8, 43, 64, 255)
        outline = (43, 128, 175, 220)

    d.rounded_rectangle(
        (490, y+27, 590, y+88),
        13,
        fill=fill,
        outline=outline,
        width=2
    )

    box = d.textbbox((0, 0), center, font=F(24, True))

    d.text(
        (540-(box[2]-box[0])/2, y+41),
        center,
        font=F(24, True),
        fill=(255, 255, 255, 255)
    )


def group_matches(matches):
    groups = []

    for m in matches:
        league = m.get("league_name", "FUTBOL")

        if not groups or groups[-1][0] != league:
            groups.append((league, []))

        groups[-1][1].append(m)

    return groups


def make_match_pages(groups):
    pages = []
    current = []
    count = 0

    for league, matches in groups:
        for m in matches:
            if count >= MAX_MATCHES:
                pages.append(current)
                current = []
                count = 0

            if current and current[-1][0] == league:
                current[-1][1].append(m)
            else:
                current.append((league, [m]))

            count += 1

    if current:
        pages.append(current)

    return pages or [[]]


def make_match_image(
    title,
    date_string,
    page_groups,
    page_no,
    total_pages
):
    dt = datetime.strptime(date_string, "%Y-%m-%d")

    count = sum(len(ms) for _, ms in page_groups)
    leagues = len(page_groups)

    height = 430 + leagues*100 + count*150 + 160

    img = Image.new(
        "RGBA",
        (W, height),
        (5, 16, 29, 255)
    )

    d = ImageDraw.Draw(img, "RGBA")

    for yy in range(height):
        ratio = yy / max(1, height-1)

        d.line(
            (0, yy, W, yy),
            fill=(
                int(5+3*ratio),
                int(17+10*ratio),
                int(30+18*ratio),
                255
            )
        )

    # Header stripes
    for x in range(-250, W+400, 190):
        d.polygon(
            [
                (x, 0),
                (x+65, 0),
                (x-170, 250),
                (x-235, 250)
            ],
            fill=(25, 125, 190, 30)
        )

    d.ellipse(
        (55, 42, 155, 142),
        fill=(10, 72, 112, 110),
        outline=(70, 185, 240, 230),
        width=3
    )

    d.text(
        (82, 59),
        "F",
        font=F(50, True),
        fill=(255, 255, 255, 255)
    )

    d.text(
        (185, 55),
        "FUTBOL OLAMI",
        font=F(48, True),
        fill=(245, 250, 255, 255)
    )

    d.text(
        (188, 112),
        "Futbol haqida hammasi!",
        font=F(21),
        fill=(130, 205, 245, 255)
    )

    d.rounded_rectangle(
        (55, 180, 205, 320),
        20,
        fill=(245, 249, 252, 255)
    )

    d.rounded_rectangle(
        (55, 180, 205, 224),
        20,
        fill=(235, 55, 55, 255)
    )

    d.rectangle(
        (55, 205, 205, 224),
        fill=(235, 55, 55, 255)
    )

    months = {
        1:"YANVAR", 2:"FEVRAL", 3:"MART", 4:"APREL",
        5:"MAY", 6:"IYUN", 7:"IYUL", 8:"AVGUST",
        9:"SENTABR", 10:"OKTABR", 11:"NOYABR", 12:"DEKABR"
    }

    days = {
        0:"DUSHANBA", 1:"SESHANBA", 2:"CHORSHANBA",
        3:"PAYSHANBA", 4:"JUMA", 5:"SHANBA", 6:"YAKSHANBA"
    }

    d.text(
        (78, 186),
        months[dt.month],
        font=F(17, True),
        fill=(255, 255, 255, 255)
    )

    d.text(
        (88, 228),
        dt.strftime("%d"),
        font=F(58, True),
        fill=(8, 25, 40, 255)
    )

    d.text(
        (245, 188),
        title,
        font=F(33, True),
        fill=(248, 252, 255, 255)
    )

    d.text(
        (248, 245),
        f"{dt.strftime('%d.%m.%Y')} | {days[dt.weekday()]}",
        font=F(19),
        fill=(145, 200, 230, 255)
    )

    if total_pages > 1:
        d.rounded_rectangle(
            (900, 188, 1018, 242),
            16,
            fill=(7, 105, 155, 235)
        )

        d.text(
            (926, 200),
            f"{page_no}/{total_pages}",
            font=F(20, True),
            fill=(255, 255, 255, 255)
        )

    y = 355

    for league, matches in page_groups:
        d.rounded_rectangle(
            (45, y, W-45, y+70),
            18,
            fill=(7, 39, 62, 255),
            outline=(45, 140, 195, 230),
            width=2
        )

        d.text(
            (70, y+20),
            league,
            font=F(23, True),
            fill=(248, 252, 255, 255)
        )

        y += 88

        for m in matches:
            draw_match(img, y, m)
            y += 150

        y += 12

    footer_y = height - 145

    d.line(
        (60, footer_y, W-60, footer_y),
        fill=(55, 135, 175, 150),
        width=2
    )

    d.text(
        (70, footer_y+25),
        "Futbol bizni birlashtiradi!",
        font=F(27, True),
        fill=(238, 248, 255, 255)
    )

    d.text(
        (70, footer_y+72),
        "Futbol olami  •  Futbol haqida hammasi!",
        font=F(20),
        fill=(125, 195, 225, 255)
    )

    return img.convert("RGB")


def send_photo(img, caption):
    buf = BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=92,
        optimize=True
    )

    buf.seek(0)

    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": CHANNEL_ID,
            "caption": caption,
            "parse_mode": "HTML"
        },
        files={
            "photo": (
                "futbol-olami.jpg",
                buf,
                "image/jpeg"
            )
        },
        timeout=30
    )

    result = r.json()

    if not result.get("ok"):
        raise Exception(str(result))


def publish_matches(date_string, title):
    matches = get_matches(date_string)
    pages = make_match_pages(group_matches(matches))

    total = len(pages)

    for no, page_groups in enumerate(pages, 1):
        img = make_match_image(
            title,
            date_string,
            page_groups,
            no,
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
            caption += f"\nSahifa: {no}/{total}"

# ---------------- STANDINGS ----------------
#
# IMPORTANT:
# API-Football Free plan blocks current-season standings/season queries.
# Therefore standings are NOT requested from API-Football.
#
# 8 leagues use ESPN's public standings endpoint (no API key required).
# Uzbekistan Super League uses the public soccerassociation.com table.
#
# To publish only when a table actually changed, we do not need persistent
# storage: at the daily 08:00 Tashkent run we check whether that league had
# a completed match yesterday. If it did, its current table is published.
# If it did not, nothing is published for that league.

ESPN_STANDINGS = [
    ("ANGLIYA — PREMIER LIGA", "eng.1"),
    ("ISPANIYA — LA LIGA", "esp.1"),
    ("ITALIYA — SERIYA A", "ita.1"),
    ("GERMANIYA — BUNDESLIGA", "ger.1"),
    ("FRANSIYA — LIGUE 1", "fra.1"),
    ("SAUDIYA ARABIYASI — SAUDI PRO LEAGUE", "ksa.1"),
    ("PORTUGALIYA — PRIMEIRA LIGA", "por.1"),
    ("NIDERLANDIYA — EREDIVISIE", "ned.1"),
]

UZ_STANDINGS_URL = "https://www.soccerassociation.com/127/"


def external_json(url, params=None):
    r = requests.get(
        url,
        params=params or {},
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 Futbol-Olami-Bot/1.0",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _stat_map(stats):
    result = {}
    if isinstance(stats, list):
        for item in stats:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("abbreviation")
            value = item.get("value")
            if name is not None:
                result[str(name).lower()] = value
    elif isinstance(stats, dict):
        for k, v in stats.items():
            result[str(k).lower()] = v
    return result


def _num(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def _find_standing_entries(node):
    if isinstance(node, dict):
        entries = node.get("entries")
        if isinstance(entries, list) and entries:
            if any(
                isinstance(x, dict) and ("team" in x or "stats" in x)
                for x in entries
            ):
                return entries
        for value in node.values():
            found = _find_standing_entries(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_standing_entries(value)
            if found:
                return found
    return None


def get_espn_standings(league_code):
    # Do NOT pass season=2026. ESPN's endpoint already returns the current
    # season and this avoids season-specific API restrictions.
    url = f"https://site.api.espn.com/apis/v2/sports/soccer/{league_code}/standings"
    data = external_json(url)
    entries = _find_standing_entries(data)

    if not entries:
        raise Exception("ESPN standings entries not found")

    table = []

    for i, entry in enumerate(entries, 1):
        team = entry.get("team", {}) or {}
        stats = _stat_map(entry.get("stats", []))

        played = _num(stats.get("gamesplayed", stats.get("gp", stats.get("played", 0))))
        wins = _num(stats.get("wins", stats.get("w", 0)))
        draws = _num(stats.get("ties", stats.get("draws", stats.get("d", 0))))
        losses = _num(stats.get("losses", stats.get("l", 0)))
        gf = _num(stats.get("goalsfor", stats.get("gf", 0)))
        ga = _num(stats.get("goalsagainst", stats.get("ga", 0)))
        gd = _num(stats.get("goaldifferential", stats.get("gd", gf - ga)), gf - ga)
        points = _num(stats.get("points", stats.get("pts", 0)))

        logos = team.get("logos") or []
        logo = None
        if logos and isinstance(logos[0], dict):
            logo = logos[0].get("href")

        table.append({
            "rank": i,
            "team": {
                "name": team.get("displayName") or team.get("name") or "?",
                "logo": logo,
            },
            "all": {
                "played": played,
                "win": wins,
                "draw": draws,
                "lose": losses,
                "goals": {"for": gf, "against": ga},
            },
            "goalsDiff": gd,
            "points": points,
        })

    # Preserve normal football sorting. The displayed table does not show GD.
    table.sort(key=lambda r: (
        -r["points"],
        -r["goalsDiff"],
        -r["all"]["goals"]["for"],
        r["team"]["name"],
    ))
    for rank, row in enumerate(table, 1):
        row["rank"] = rank

    return table


class SimpleTableParser:
    """Small stdlib-only HTML table parser for the Uzbekistan source."""
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_tr = False
            self.in_cell = False
            self.rows = []
            self.current = []
            self.text = []
            self.cell_tag = None

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag == "table":
                self.in_table = True
            elif self.in_table and tag == "tr":
                self.in_tr = True
                self.current = []
            elif self.in_tr and tag in ("td", "th"):
                self.in_cell = True
                self.cell_tag = tag
                self.text = []

        def handle_data(self, data):
            if self.in_cell:
                self.text.append(data)

        def handle_endtag(self, tag):
            tag = tag.lower()
            if self.in_cell and tag == self.cell_tag:
                value = " ".join("".join(self.text).split())
                self.current.append(value)
                self.text = []
                self.in_cell = False
                self.cell_tag = None
            elif self.in_tr and tag == "tr":
                if self.current:
                    self.rows.append(self.current)
                self.current = []
                self.in_tr = False
            elif self.in_table and tag == "table":
                self.in_table = False


def get_uzbekistan_standings():
    r = requests.get(
        UZ_STANDINGS_URL,
        headers={"User-Agent": "Mozilla/5.0 Futbol-Olami-Bot/1.0"},
        timeout=30,
    )
    r.raise_for_status()

    parser = SimpleTableParser.Parser()
    parser.feed(r.text)

    # Find a table containing Team and points. Different page versions may
    # use slightly different header labels.
    chosen = None
    for idx, row in enumerate(parser.rows):
        low = [x.lower() for x in row]
        if "team" in low and any(x in low for x in ("pts", "points", "p")):
            chosen = parser.rows[idx + 1:]
            break

    if not chosen:
        raise Exception("Uzbekistan standings table not found")

    table = []
    for row in chosen:
        if len(row) < 2:
            continue

        # Expected full table:
        # No, Team, Played, W, D, L, GF, GA, GD, Pts
        try:
            rank = int(row[0].strip())
        except Exception:
            continue

        def ri(i):
            return _num(row[i]) if i < len(row) else 0

        team_name = row[1].strip()
        played = ri(2)
        wins = ri(3)
        draws = ri(4)
        losses = ri(5)
        gf = ri(6)
        ga = ri(7)
        gd = ri(8) if len(row) > 8 else gf - ga
        points = ri(9) if len(row) > 9 else 0

        table.append({
            "rank": rank,
            "team": {"name": team_name, "logo": None},
            "all": {
                "played": played,
                "win": wins,
                "draw": draws,
                "lose": losses,
                "goals": {"for": gf, "against": ga},
            },
            "goalsDiff": gd,
            "points": points,
        })

    if not table:
        raise Exception("Uzbekistan standings rows not found")

    table.sort(key=lambda r: r["rank"])
    return table


def draw_standing_row(img, y, row):
    d = ImageDraw.Draw(img, "RGBA")

    rank = row.get("rank", "")
    team = row.get("team", {})
    name = short_name(team.get("name", "?"))

    played = row.get("all", {}).get("played", 0)
    wins = row.get("all", {}).get("win", 0)
    draws = row.get("all", {}).get("draw", 0)
    losses = row.get("all", {}).get("lose", 0)

    goals = row.get("all", {}).get("goals", {})
    gf = goals.get("for", 0)
    ga = goals.get("against", 0)
    points = row.get("points", 0)

    fill = (7, 31, 49, 255) if int(rank or 0) % 2 else (8, 37, 57, 255)
    if int(rank or 0) in (1, 2, 3, 4):
        fill = (8, 48, 70, 255)

    d.rounded_rectangle(
        (45, y, W-45, y+92),
        14,
        fill=fill,
        outline=(34, 105, 145, 180),
        width=1,
    )

    d.text((68, y+27), str(rank), font=F(25, True), fill=(245, 250, 255, 255))
    draw_logo(img, team.get("logo"), 145, y+46, 58)

    team_text, team_font = fit_text(d, name, 330, start=24, minimum=17)
    d.text((190, y+30), team_text, font=team_font, fill=(248, 252, 255, 255))

    values = [
        (555, str(played)),
        (635, str(wins)),
        (710, str(draws)),
        (785, str(losses)),
        (865, f"{gf}:{ga}"),
        (950, str(points)),
    ]

    for x, value in values:
        box = d.textbbox((0, 0), value, font=F(21, True))
        d.text(
            (x-(box[2]-box[0])/2, y+33),
            value,
            font=F(21, True),
            fill=(235, 246, 252, 255),
        )


def make_standings_image(title, season, table, page_no=1, total_pages=1):
    rows = table[:20]
    height = 330 + len(rows)*102 + 150

    img = Image.new("RGBA", (W, height), (5, 16, 29, 255))
    d = ImageDraw.Draw(img, "RGBA")

    for yy in range(height):
        ratio = yy / max(1, height-1)
        d.line(
            (0, yy, W, yy),
            fill=(int(5+3*ratio), int(17+10*ratio), int(30+18*ratio), 255),
        )

    for x in range(-250, W+400, 190):
        d.polygon(
            [(x, 0), (x+65, 0), (x-170, 220), (x-235, 220)],
            fill=(25, 125, 190, 30),
        )

    d.ellipse((55, 40, 155, 140), fill=(10, 72, 112, 110), outline=(70, 185, 240, 230), width=3)
    d.text((82, 57), "F", font=F(50, True), fill=(255, 255, 255, 255))
    d.text((185, 52), "FUTBOL OLAMI", font=F(47, True), fill=(245, 250, 255, 255))
    d.text((188, 108), "Futbol haqida hammasi!", font=F(21), fill=(130, 205, 245, 255))

    d.text((55, 178), title, font=F(34, True), fill=(248, 252, 255, 255))
    d.text((58, 225), f"{season}/{season+1} MAVSUMI", font=F(20), fill=(145, 200, 230, 255))

    if total_pages > 1:
        d.rounded_rectangle((900, 175, 1018, 229), 16, fill=(7, 105, 155, 235))
        d.text((926, 187), f"{page_no}/{total_pages}", font=F(20, True), fill=(255, 255, 255, 255))

    y = 275
    d.rounded_rectangle((45, y, W-45, y+55), 13, fill=(7, 63, 91, 255), outline=(45, 140, 195, 230), width=2)

    headers = [
        (78, "#"), (195, "JAMOA"),
        (555, "I"), (635, "V"), (710, "N"), (785, "P"),
        (865, "G"), (950, "O"),
    ]
    for x, text in headers:
        box = d.textbbox((0, 0), text, font=F(18, True))
        d.text((x-(box[2]-box[0])/2 if x != 195 else x, y+16), text, font=F(18, True), fill=(175, 225, 245, 255))

    y += 68
    for row in rows:
        draw_standing_row(img, y, row)
        y += 102

    footer_y = height - 125
    d.line((60, footer_y, W-60, footer_y), fill=(55, 135, 175, 150), width=2)
    d.text((70, footer_y+23), "Futbol bizni birlashtiradi!", font=F(27, True), fill=(238, 248, 255, 255))
    d.text((70, footer_y+68), "I — o‘yinlar  •  V — g‘alaba  •  N — durang  •  P — mag‘lubiyat  •  G — gollar (zabito:propusheno)  •  O — ochko", font=F(16), fill=(125, 195, 225, 255))

    return img.convert("RGB")


def espn_had_match_yesterday(league_code, date_obj):
    date_string = date_obj.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/scoreboard"
    data = external_json(url, {"dates": date_string})
    events = data.get("events", []) if isinstance(data, dict) else []

    for event in events:
        competitions = event.get("competitions") or []
        for comp in competitions:
            status = (comp.get("status") or {}).get("type") or {}
            state = status.get("state")
            if state == "post":
                return True

    return False


def api_football_had_match_yesterday(league_id, date_obj):
    # Date-only fixtures are available on the user's current API-Football
    # setup even though current-season /standings and season queries are not.
    fixtures = api_get(
        "fixtures",
        {
            "date": date_obj.strftime("%Y-%m-%d"),
            "timezone": "Asia/Tashkent",
        },
    )

    for m in fixtures:
        league = m.get("league", {})
        if league.get("id") != league_id:
            continue
        if status_of(m) == "finished":
            return True

    return False


def publish_standing_table(title, season, table):
    page_size = 20
    pages = [table[i:i+page_size] for i in range(0, len(table), page_size)]
    total = len(pages)

    for page_no, rows in enumerate(pages, 1):
        img = make_standings_image(title, season, rows, page_no, total)
        caption = (
            f"<b>FUTBOL OLAMI</b>\n"
            f"📊 {title}\n"
            f"Mavsum: {season}/{season+1}"
        )
        if total > 1:
            caption += f"\nSahifa: {page_no}/{total}"
        send_photo(img, caption)


def publish_standings(date_obj):
    season = date_obj.year if date_obj.month >= 7 else date_obj.year - 1
    checked = 0
    changed = 0

    # Eight leagues: ESPN table + ESPN yesterday-scoreboard check.
    for title, league_code in ESPN_STANDINGS:
        checked += 1
        try:
            if not espn_had_match_yesterday(league_code, date_obj - timedelta(days=1)):
                print("STANDINGS NO CHANGE:", title, "no completed match yesterday")
                continue

            table = get_espn_standings(league_code)
            if not table:
                raise Exception("empty ESPN standings table")

            publish_standing_table(title, season, table)
            changed += 1
            print("STANDINGS OK:", title, len(table))
        except Exception as e:
            print("STANDINGS ERROR:", title, str(e))

    # Uzbekistan: API-Football date-only check + public current table.
    checked += 1
    try:
        if not api_football_had_match_yesterday(278, date_obj - timedelta(days=1)):
            print("STANDINGS NO CHANGE: O‘ZBEKISTON — SUPER LIGA no completed match yesterday")
        else:
            table = get_uzbekistan_standings()
            if not table:
                raise Exception("empty Uzbekistan standings table")
            publish_standing_table("O‘ZBEKISTON — SUPER LIGA", date_obj.year, table)
            changed += 1
            print("STANDINGS OK: O‘ZBEKISTON — SUPER LIGA", len(table))
    except Exception as e:
        print("STANDINGS ERROR: O‘ZBEKISTON — SUPER LIGA", str(e))

    print("STANDINGS CHECK COMPLETE, CHECKED:", checked, "CHANGED:", changed)


def run_bot():
    now = datetime.now(TASHKENT)
    today = now.date()
    yesterday = today - timedelta(days=1)

    publish_matches(yesterday.strftime("%Y-%m-%d"), "KECHAGI O‘YINLAR NATIJALARI")
    publish_matches(today.strftime("%Y-%m-%d"), "BUGUNGI O‘YINLAR")
    publish_standings(today)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("authorization", "")

        if not CRON_SECRET or auth != f"Bearer {CRON_SECRET}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        try:
            run_bot()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": "Futbol olami cron completed"}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            print("CRON ERROR:", e)
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8"))
