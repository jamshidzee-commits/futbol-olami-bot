
import os
import io
import json
import html
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps
from http.server import BaseHTTPRequestHandler

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

# Faqat rasmga sig‘adigan miqdor. Kerak bo‘lsa keyin ko‘paytiramiz.
MAX_TODAY_MATCHES = 24
MAX_YESTERDAY_MATCHES = 18

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def font(size, bold=True):
    path = FONT_BOLD if bold else FONT_REG
    return ImageFont.truetype(path, size)

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

def get_selected_fixtures(date_string):
    fixtures = api_get("fixtures", {
        "date": date_string,
        "timezone": "Asia/Tashkent",
    })
    result = []
    for m in fixtures:
        league = m.get("league", {})
        lid = league.get("id")
        country = league.get("country", "")
        if lid in LEAGUE_IDS:
            m["league_name"] = LEAGUE_IDS[lid]
            result.append(m)
        elif country == "Uzbekistan":
            m["league_name"] = "O‘ZBEKISTON — " + league.get("name", "FUTBOL").upper()
            result.append(m)
    result.sort(key=lambda x: (x.get("league_name",""), x.get("fixture",{}).get("date","")))
    return result

def get_logo(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print("logo error:", e)
        return None

def fit_logo(im, size=54):
    if im is None:
        return None
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0,0,0,0))
    x=(size-im.width)//2
    y=(size-im.height)//2
    canvas.alpha_composite(im, (x,y))
    return canvas

def text_width(draw, text, f):
    box = draw.textbbox((0,0), text, font=f)
    return box[2]-box[0]

def draw_centered(draw, text, y, f, fill):
    w=text_width(draw,text,f)
    draw.text(((1080-w)//2,y), text, font=f, fill=fill)

def make_background(h):
    img=Image.new("RGB",(1080,h),(4,14,28))
    p=img.load()
    for y in range(h):
        t=y/max(1,h-1)
        for x in range(1080):
            glow=max(0,1-((x-540)**2+(y-h*0.78)**2)**0.5/900)
            p[x,y]=(4+int(3*t),13+int(12*t),27+int(22*t)+int(12*glow))
    d=ImageDraw.Draw(img,"RGBA")
    # subtle diagonal geometry
    for i in range(-500,1500,180):
        d.polygon([(i,0),(i+70,0),(i-250,h),(i-320,h)],fill=(20,105,170,20))
    # stadium glow at bottom
    for rad in range(600,80,-12):
        a=max(3,int((600-rad)*0.18))
        d.ellipse((540-rad,h-125-rad*0.23,540+rad,h-125+rad*0.23),
                  outline=(30,150,230,a),width=3)
    d.rectangle((0,h-330,1080,h),fill=(2,24,31,110))
    return img

def draw_header(img, title, date_obj, live=False):
    d=ImageDraw.Draw(img,"RGBA")
    # football icon
    d.ellipse((48,42,150,144),fill=(10,110,190,45),outline=(60,190,255,180),width=3)
    d.ellipse((66,60,132,126),outline=(210,235,255,180),width=2)
    d.polygon([(99,77),(114,88),(110,105),(91,105),(86,89)],fill=(245,248,250,245))
    d.text((175,48),"FUTBOL OLAMI",font=font(52),fill=(245,250,255,255))
    d.text((178,108),"FUTBOL HAQIDA HAMMASI!",font=font(21,False),fill=(150,215,245,255))

    y=175
    d.rounded_rectangle((42,y,1038,y+118),25,fill=(5,28,47,240),outline=(40,145,205,190),width=2)
    month=date_obj.strftime("%B").upper()
    # Uzbek month mapping
    months={1:"YANVAR",2:"FEVRAL",3:"MART",4:"APREL",5:"MAY",6:"IYUN",7:"IYUL",
            8:"AVGUST",9:"SENTABR",10:"OKTABR",11:"NOYABR",12:"DEKABR"}
    month=months[date_obj.month]
    d.rounded_rectangle((62,y+18,210,y+100),15,fill=(245,250,255,255))
    d.rounded_rectangle((62,y+18,210,y+45),15,fill=(235,55,55,255))
    d.rectangle((62,y+33,210,y+45),fill=(235,55,55,255))
    d.text((84,y+19),month,font=font(16),fill=(255,255,255,255))
    day=str(date_obj.day)
    d.text((94,y+43),day,font=font(40),fill=(8,25,40,255))

    d.text((245,y+15),title,font=font(34),fill=(250,252,255,255))
    weekday={0:"DUSHANBA",1:"SESHANBA",2:"CHORSHANBA",3:"PAYSHANBA",
             4:"JUMA",5:"SHANBA",6:"YAKSHANBA"}[date_obj.weekday()]
    d.text((245,y+64),f"{date_obj.strftime('%d.%m.%Y')}  |  {weekday}",
           font=font(20,False),fill=(155,205,235,255))
    if live:
        d.rounded_rectangle((875,y+28,1015,y+76),14,fill=(235,48,48,255))
        d.ellipse((892,y+45,906,y+59),fill=(255,255,255,255))
        d.text((918,y+34),"LIVE",font=font(22),fill=(255,255,255,255))

def draw_league(d, y, league_name):
    d.rounded_rectangle((45,y,1035,y+58),15,fill=(7,35,53,250),outline=(40,120,165,160),width=2)
    d.text((68,y+15),league_name,font=font(21),fill=(245,250,255,255))
    return y+64

def draw_match(d, img, y, match, completed):
    # row
    d.rounded_rectangle((52,y,1028,y+72),12,fill=(3,21,36,215))
    d.line((70,y+71,1010,y+71),fill=(40,105,140,100),width=1)

    fixture=match.get("fixture",{})
    tm=fixture.get("date","")
    time=tm[11:16] if len(tm)>=16 else "--:--"
    status=fixture.get("status",{}).get("short","")
    elapsed=fixture.get("status",{}).get("elapsed")
    home=match.get("teams",{}).get("home",{})
    away=match.get("teams",{}).get("away",{})
    hn=home.get("name","?")
    an=away.get("name","?")
    hs=match.get("goals",{}).get("home")
    ass=match.get("goals",{}).get("away")

    d.text((68,y+23),time,font=font(19),fill=(220,235,245,255))

    # team names
    d.text((180,y+14),hn,font=font(18),fill=(245,248,252,255))
    d.text((180,y+39),an,font=font(18),fill=(245,248,252,255))

    hlogo=fit_logo(get_logo(home.get("logo")),48)
    alogo=fit_logo(get_logo(away.get("logo")),48)
    if hlogo: img.alpha_composite(hlogo,(535,y+8))
    if alogo: img.alpha_composite(alogo,(535,y+34))

    if status in ["FT","AET","P"]:
        score=f"{hs if hs is not None else 0} : {ass if ass is not None else 0}"
        d.rounded_rectangle((690,y+12,810,y+58),9,fill=(4,34,55,255),outline=(30,125,175,180),width=2)
        sw=text_width(d,score,font(21))
        d.text((750-sw//2,y+20),score,font=font(21),fill=(255,255,255,255))
    elif status in ["1H","2H","HT","ET","BT","P"]:
        score=f"{hs or 0} : {ass or 0}"
        d.text((690,y+10),f"🔴 {elapsed or ''}'",font=font(16),fill=(255,85,85,255))
        d.text((690,y+34),score,font=font(21),fill=(255,255,255,255))
    else:
        d.text((690,y+25),"VS",font=font(20),fill=(75,190,245,255))

    # compact status label
    if status in ["1H","2H","HT","ET","BT","P"]:
        d.text((860,y+25),"LIVE",font=font(16),fill=(255,90,90,255))

    return y+78

def create_fixture_image(matches, title, date_string, max_matches):
    date_obj=datetime.strptime(date_string,"%Y-%m-%d").date()
    # reserve approx 140px per league header + rows; cap data
    matches=matches[:max_matches]
    leagues=[]
    for m in matches:
        if m["league_name"] not in leagues: leagues.append(m["league_name"])
    h=390 + len(matches)*78 + len(leagues)*64 + 180
    img=make_background(h).convert("RGBA")
    draw_header(img,title,date_obj,any(m.get("fixture",{}).get("status",{}).get("short") in ["1H","2H","HT","ET","BT","P"] for m in matches))
    d=ImageDraw.Draw(img,"RGBA")
    y=325
    current=None
    for m in matches:
        league=m["league_name"]
        if league!=current:
            y=draw_league(d,y,league)
            current=league
        y=draw_match(d,img,y,m,False)
    # footer
    d.text((70,h-120),"Futbol bizni birlashtiradi!",font=font(28),fill=(235,248,255,255))
    d.text((70,h-78),"Futbol olami  •  Futbol haqida hammasi!",font=font(18,False),fill=(125,195,230,255))
    return img

def send_photo(img, caption):
    buf=io.BytesIO()
    img.save(buf,format="PNG",optimize=True)
    buf.seek(0)
    url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    r=requests.post(
        url,
        data={"chat_id":CHANNEL_ID,"caption":caption,"parse_mode":"HTML"},
        files={"photo":("futbol-olami.png",buf,"image/png")},
        timeout=45,
    )
    result=r.json()
    if not result.get("ok"):
        raise Exception(str(result))
    return result

def send_text(text):
    url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r=requests.post(url,json={
        "chat_id":CHANNEL_ID,"text":text,"parse_mode":"HTML"
    },timeout=20)
    result=r.json()
    if not result.get("ok"):
        raise Exception(str(result))
    return result

def run_bot():
    now=datetime.now(TASHKENT)
    today=now.date()
    yesterday=today-timedelta(days=1)

    ystr=yesterday.strftime("%Y-%m-%d")
    tstr=today.strftime("%Y-%m-%d")

    ymatches=get_selected_fixtures(ystr)
    tmatches=get_selected_fixtures(tstr)

    # Only create/send image if there are matches.
    if ymatches:
        img=create_fixture_image(
            ymatches,
            "KECHAGI O‘YINLAR NATIJALARI",
            ystr,
            MAX_YESTERDAY_MATCHES
        )
        send_photo(
            img,
            "🏁 <b>KECHAGI O‘YINLAR NATIJALARI</b>\n"
            "📅 " + yesterday.strftime("%d.%m.%Y")
        )
    else:
        send_text(
            "⚽ <b>FUTBOL OLAMI</b>\n\n"
            "Kecha tanlangan musobaqalarda o‘yinlar bo‘lmadi."
        )

    if tmatches:
        img=create_fixture_image(
            tmatches,
            "BUGUNGI O‘YINLAR",
            tstr,
            MAX_TODAY_MATCHES
        )
        send_photo(
            img,
            "⚽ <b>BUGUNGI O‘YINLAR</b>\n"
            "📅 " + today.strftime("%d.%m.%Y")
        )
    else:
        send_text(
            "⚽ <b>FUTBOL OLAMI</b>\n\n"
            "Bugun tanlangan musobaqalarda o‘yinlar yo‘q."
        )

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        authorization=self.headers.get("authorization","")
        if not CRON_SECRET or authorization != f"Bearer {CRON_SECRET}":
            self.send_response(401)
            self.send_header("Content-Type","text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return
        try:
            run_bot()
            body=json.dumps({"ok":True,"message":"Futbol olami image cron completed"},ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        except Exception as e:
            print("CRON ERROR:",e)
            body=json.dumps({"ok":False,"error":str(e)},ensure_ascii=False)
            self.send_response(500)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
