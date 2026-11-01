#!/usr/bin/env python3
import os, sys, re, glob, json, time, math, random, asyncio, logging, argparse, subprocess, urllib.parse, wave
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("NexoraWorld")

# ================= 1. BRANDING & CREDENTIALS =================
def _clean(v): return (v or "").strip().strip('"').strip("'").strip()
GEMINI_API_KEY = _clean(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean(os.environ.get("YT_REFRESH_TOKEN", ""))

CHANNEL_NAME = "NEXORA NEWS"
TAGLINE = "THE WORLD. THE NEXT. THE NEWS."
SUB_TAGLINE = "GLOBAL COVERAGE | INDEPENDENT | VERIFIED"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
TOPIC_ANALYTICS_FILE = os.path.join("assets", "topic_analytics.json")
LOGO_PATH = os.path.join("assets", "channel_logo.png")

GLOBAL_TOPICS = {
    "GEOPOLITICS": ["united nations", "white house", "biden", "trump", "putin", "kremlin", "nato", "eu", "diplomacy", "summit", "treaty", "sanctions", "china", "taiwan"],
    "DEFENSE_SECURITY": ["military", "pentagon", "defense", "missile", "navy", "warship", "fighter jet", "aircraft carrier", "army", "conflict", "air force", "security"],
    "GLOBAL_ECONOMY": ["federal reserve", "central bank", "inflation", "oil", "trade", "tariffs", "wall street", "stock market", "imf", "world bank", "dollar", "gdp"],
    "WORLD_TECH_AI": ["artificial intelligence", "nasa", "spacex", "satellite", "semiconductor", "chip", "quantum", "cyber", "robotics", "tech", "data center"],
    "CLIMATE_CRISIS": ["climate", "summit", "green energy", "cop", "wildfire", "hurricane", "renewable", "earthquake", "environment"]
}

ENTITY_MAP_INTL = [
    (["white house", "president", "biden", "trump", "washington", "congress", "capitol"], "White House Washington DC press briefing President United States"),
    (["united nations", "un security council", "un general assembly", "geneva", "guterres"], "United Nations Security Council chamber Geneva New York diplomacy"),
    (["nato", "pentagon", "defense secretary", "allies", "brussels"], "NATO headquarters summit Brussels defense ministers alliance meeting"),
    (["aircraft carrier", "navy", "warship", "fighter jet", "stealth bomber", "air force"], "Modern aircraft carrier warship operations at sea military fighter jet launch"),
    (["space", "nasa", "spacex", "rocket", "launch", "satellite", "astronaut", "moon", "mars"], "NASA rocket launch Cape Canaveral space exploration satellite deployment"),
    (["kremlin", "russia", "putin", "moscow", "ukraine"], "Kremlin Red Square Moscow official government architecture"),
    (["china", "beijing", "xi jinping", "taiwan", "south china sea"], "Great Hall of the People Beijing China official international diplomacy"),
    (["artificial intelligence", "ai", "supercomputer", "chips", "semiconductor", "nvidia"], "Advanced artificial intelligence high tech data center server architecture"),
    (["wall street", "stock exchange", "economy", "federal reserve", "central bank", "treasury"], "New York Stock Exchange Wall Street financial trading floor"),
    (["europe", "european union", "brussels", "london", "downing street", "parliament"], "Palace of Westminster UK Parliament London Downing Street"),
    (["middle east", "israel", "gaza", "iran", "red sea", "diplomacy"], "Middle East diplomatic negotiations peace summit regional security"),
    (["climate", "renewable", "solar", "wind", "electric", "environment"], "Renewable energy wind turbines solar farm modern climate technology")
]

def map_headline_to_search_query(headline):
    hl = (headline or "").lower()
    for keywords, query in ENTITY_MAP_INTL:
        if any(kw in hl for kw in keywords):
            return query
    return "International diplomatic press conference global news report"

NEWS_FEEDS_INTL = {
    "WORLD": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.aljazeera.net/xml/rss/all.xml",
    ],
    "TECHNOLOGY": [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "DEFENSE": [
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ]
}

EDITION_CONFIGS = {
    "MORNING": {"target_count": 8, "title_prefix": "🔴 LIVE Morning Global Briefing: Top 8 World News", "bulletin_label": "GLOBAL BRIEFING"},
    "AFTERNOON": {"target_count": 8, "title_prefix": "🔴 LIVE Global In-Depth: Top World Developments", "bulletin_label": "WORLD IN-DEPTH"},
    "EVENING": {"target_count": 8, "title_prefix": "🔴 LIVE Prime Time World Bulletin: Top 8 Stories", "bulletin_label": "PRIME TIME WORLD"},
}

def get_current_edition():
    try:
        h = datetime.now(timezone.utc).hour
        return "MORNING" if 4 <= h < 12 else ("AFTERNOON" if 12 <= h < 18 else "EVENING")
    except Exception: return "MORNING"

# ================= 2. TYPOGRAPHY & TEXT ENGINE =================
def _get_font(size=28, bold=True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def wrap_text_to_width(draw, text, font, max_w, max_lines=2):
    words = (text or "").split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_w:
            cur.append(w)
        else:
            if cur: lines.append(" ".join(cur))
            cur = [w]
    if cur: lines.append(" ".join(cur))
    return lines[:max_lines]

# ================= 3. TOPIC ANALYTICS FEEDBACK LOOP =================
def classify_headline_topic(headline):
    hl = (headline or "").lower()
    for cat, kws in GLOBAL_TOPICS.items():
        if any(kw in hl for kw in kws): return cat
    return "GLOBAL_AFFAIRS"

def load_topic_analytics():
    if os.path.exists(TOPIC_ANALYTICS_FILE):
        try: return json.load(open(TOPIC_ANALYTICS_FILE, "r", encoding="utf-8"))
        except Exception: pass
    return {"version": "3.0", "channel_name": CHANNEL_NAME, "recommended_topic": "GEOPOLITICS", "topic_performance": {}}

def save_topic_analytics(data):
    try:
        os.makedirs("assets", exist_ok=True)
        json.dump(data, open(TOPIC_ANALYTICS_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e: logger.warning(f"Could not save analytics: {e}")

def get_recommended_topic():
    adata = load_topic_analytics()
    return adata.get("recommended_topic", "GEOPOLITICS")

# ================= 4. GROUND PHOTO ENGINE (GLOBAL PHOTOJOURNALISM) =================
def _validate_image(raw_bytes, target_w, target_h):
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size
    if w < 180 or h < 140: raise ValueError("Image too small")
    tr, sr = target_w / float(target_h), w / float(h)
    if sr > tr:
        nw = int(h * tr)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / tr)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.08)).enhance(1.08)

def _fetch_article_og_image(url):
    if not url or not url.startswith("http"): return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=4, allow_redirects=True)
        if r.status_code == 200:
            m = re.search(r'<meta[^>]+content=[\"\'](https?://[^\"\']+)[\"\']', r.text, re.IGNORECASE)
            if m:
                u = m.group(1)
                if not any(k in u.lower() for k in ["google", "gstatic", "1x1", "pixel", "favicon", "avatar"]):
                    ir = requests.get(u, headers=HEADERS, timeout=4)
                    if ir.status_code == 200 and len(ir.content) > 12000:
                        return ir.content
    except Exception: pass
    return None

def _fetch_ground_news_photo(headline, target_w, target_h):
    q = map_headline_to_search_query(headline)
    try:
        url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(q)}&gsrlimit=10&prop=imageinfo&iiprop=url|mime|size&format=json"
        res = requests.get(url, headers=HEADERS, timeout=5).json()
        pages = res.get("query", {}).get("pages", {})
        for _, page in pages.items():
            info = page.get("imageinfo", [{}])[0]
            u = info.get("url", "")
            title_l = page.get("title", "").lower()
            if any(k in title_l for k in ["book", "document", "scan", "archive", "drawing", "map", "flag", "1800", "1900", "1920", "1940"]):
                continue
            if u.lower().endswith((".jpg", ".jpeg", ".png")) and info.get("width", 0) >= 600:
                ir = requests.get(u, headers=HEADERS, timeout=6)
                if ir.status_code == 200: return _validate_image(ir.content, target_w, target_h)
    except Exception: pass
    return None

def _fetch_pollinations_image(prompt, target_w, target_h):
    mapped_q = map_headline_to_search_query(prompt)
    clean_p = f"high quality real global photojournalism press photography of {mapped_q}, cinematic lighting, photorealistic, raw news footage, 8k, highly detailed realistic texture, no text, no captions, authentic international press broadcast background"
    u = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_p)}?width={target_w}&height={target_h}&nologo=true&model=flux"
    try:
        r = requests.get(u, timeout=14)
        if r.status_code == 200 and len(r.content) > 15000:
            return _validate_image(r.content, target_w, target_h)
    except Exception: pass
    return None

def create_broadcast_story_card(output_path, target_w=1100, target_h=740, headline="", counter="STORY 1 OF 5", category="WORLD", location="GLOBAL DESK", bulletin="LIVE", base_img=None, is_short=False, **kwargs):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    card = Image.new("RGB", (target_w, target_h), (8, 14, 28))

    if base_img:
        try:
            resized_base = _validate_image(base_img.tobytes() if hasattr(base_img, "tobytes") else base_img, target_w, target_h)
            card.paste(resized_base, (0, 0))
        except Exception:
            try: card.paste(base_img.resize((target_w, target_h), Image.Resampling.LANCZOS), (0, 0))
            except Exception: pass
    else:
        b_draw = ImageDraw.Draw(card)
        for y in range(target_h):
            r = int(10 + (y / target_h) * 16)
            g = int(18 + (y / target_h) * 22)
            b = int(45 + (y / target_h) * 45)
            b_draw.line([(0, y), (target_w, y)], fill=(r, g, b))
        for r_size in [120, 240, 360, 480, 600]:
            b_draw.ellipse([target_w // 2 - r_size, target_h // 2 - r_size, target_w // 2 + r_size, target_h // 2 + r_size], outline=(24, 48, 100), width=1)

    grad = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grad)
    for y in range(int(target_h * 0.45), target_h):
        ratio = (y - target_h * 0.45) / (target_h * 0.55)
        alpha = int(ratio * ratio * 230)
        g_draw.line([(0, y), (target_w, y)], fill=(6, 10, 22, alpha))
    card = Image.alpha_composite(card.convert("RGBA"), grad).convert("RGB")

    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, target_w - 1, target_h - 1], outline=(255, 215, 0), width=3)
    draw.rectangle([3, 3, target_w - 4, target_h - 4], outline=(220, 20, 36), width=2)

    top_badge_text = f"{bulletin}  |  {counter.upper()}"
    font_top = _get_font(20, bold=True)
    bbox = draw.textbbox((0, 0), top_badge_text, font=font_top)
    bw = (bbox[2] - bbox[0]) + 60
    draw.rounded_rectangle([20, 20, 20 + bw, 68], radius=8, fill=(185, 14, 28), outline=(255, 215, 0), width=2)
    draw.ellipse([34, 36, 48, 50], fill=(255, 255, 255))
    draw.ellipse([37, 39, 45, 47], fill=(235, 20, 36))
    draw.text((56, 32), top_badge_text, font=font_top, fill=(255, 255, 255))

    draw.rounded_rectangle([target_w - 280, 20, target_w - 20, 68], radius=8, fill=(10, 24, 58), outline=(0, 210, 255), width=2)
    draw.text((target_w - 260, 34), "NEXORA GLOBAL DESK", font=_get_font(18, bold=True), fill=(0, 220, 255))

    strap_h = 160 if is_short else 145
    sy = target_h - strap_h - 20
    draw.rectangle([18, sy, target_w - 18, target_h - 20], fill=(8, 14, 28))
    draw.rectangle([18, sy - 4, target_w - 18, sy], fill=(255, 215, 0))

    kicker_text = f" {location.upper()}  |  {category.upper()} "
    k_font = _get_font(18, bold=True)
    k_bbox = draw.textbbox((0, 0), kicker_text, font=k_font)
    kw = (k_bbox[2] - k_bbox[0]) + 20
    draw.rounded_rectangle([28, sy + 10, 28 + kw, sy + 44], radius=6, fill=(210, 16, 30))
    draw.text((38, sy + 16), kicker_text, font=k_font, fill=(255, 255, 255))

    clean_hl = re.sub(r'^(BREAKING|EXPLAINER|ANALYSIS|WATCH|UPDATE|EXCLUSIVE|PHOTOS?|VIDEO)\s*[:|-]\s*', '', headline or '', flags=re.IGNORECASE).strip()
    clean_hl = re.sub(r'\s*-\s*[^-]+$', '', clean_hl).strip()
    clean_hl = re.sub(r'\s*[:|-]?\s*(What to know|Why it matters|What we know|Explained|Read more).*$', '', clean_hl, flags=re.IGNORECASE).strip()

    lines = wrap_text_to_width(draw, clean_hl, _get_font(34 if is_short else 30, bold=True), target_w - 70, max_lines=2)
    if lines:
        draw.text((32, sy + 58), lines[0], font=_get_font(34 if is_short else 30, bold=True), fill=(255, 255, 255))
    if len(lines) > 1:
        draw.text((32, sy + 102), lines[1], font=_get_font(30 if is_short else 26, bold=True), fill=(255, 225, 60))

    card.save(output_path, "JPEG", quality=95)
    return output_path

def download_scene_image(output_path, prompt="", rss_url="", rss_image_url="", article_url="", headline="", counter="STORY 1", category="WORLD", location="GLOBAL DESK", bulletin="LIVE", is_short=True, scene_idx=0, **kwargs):
    tw, th = (1080, 830) if is_short else (1100, 740)
    rss_url = rss_url or rss_image_url or ""
    base = None

    if rss_url and rss_url.startswith("http") and not any(k in rss_url.lower() for k in ["google", "gstatic", "1x1", "pixel"]):
        try:
            r = requests.get(rss_url, headers=HEADERS, timeout=6)
            if r.status_code == 200 and len(r.content) > 12000: base = _validate_image(r.content, tw, th)
        except Exception: pass

    if base is None and article_url:
        art = _fetch_article_og_image(article_url)
        if art:
            try: base = _validate_image(art, tw, th)
            except Exception: pass

    if base is None: base = _fetch_ground_news_photo(headline or prompt, tw, th)
    if base is None: base = _fetch_pollinations_image(prompt or headline, tw, th)

    if base and (scene_idx == 0 or not os.path.exists("temp/lead_raw_photo.jpg")):
        try: base.save("temp/lead_raw_photo.jpg", "JPEG", quality=95)
        except Exception: pass

    return create_broadcast_story_card(output_path, target_w=tw, target_h=th, headline=headline, counter=counter, category=category, location=location, bulletin=bulletin, base_img=base, is_short=is_short)

# ================= 5. REAL STUDIO ANCHOR VIDEO ENGINE =================
class RealStudioAnchor:
    def __init__(self, video_path, target_w=760, target_h=900):
        self.w, self.h, self.frames = target_w, target_h, []
        try:
            p_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_path]
            orig_sz = subprocess.check_output(p_cmd).decode().strip()
            ow, oh = [int(v) for v in orig_sz.split("x")]
            ar_target, ar_orig = target_w / float(target_h), ow / float(oh)
            if ar_orig > ar_target:
                crop_w = int(oh * ar_target)
                vf = f"crop={crop_w}:{oh}:(in_w-{crop_w})/2:0,scale={target_w}:{target_h}"
            else:
                crop_h = int(ow / ar_target)
                vf = f"crop={ow}:{crop_h}:0:(in_h-{crop_h})/2,scale={target_w}:{target_h}"

            cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            f_size = target_w * target_h * 3
            while True:
                buf = proc.stdout.read(f_size)
                if not buf or len(buf) < f_size: break
                self.frames.append(Image.frombytes("RGB", (target_w, target_h), buf))
            proc.stdout.close()
            proc.wait()
            logger.info(f"✅ Loaded International Real Anchor: {len(self.frames)} frames cached at {target_w}x{target_h}")
        except Exception as e:
            logger.warning(f"Real studio anchor fallback: {e}")

    @property
    def total(self): return len(self.frames)

    def get_frame(self, frame_idx):
        if not self.frames:
            img = Image.new("RGB", (self.w, self.h), (18, 28, 64))
            ImageDraw.Draw(img).text((self.w // 2 - 120, self.h // 2), f"🔴 {CHANNEL_NAME}", font=_get_font(32, bold=True), fill=(255, 215, 0))
            return img
        return self.frames[frame_idx % len(self.frames)]

def find_real_anchor_video(gender="female"):
    g = (gender or "female").lower()
    for p in [f"anchor_real_{g}.mp4", f"assets/anchor_real_{g}.mp4", "anchor_real.mp4", "anchor_studio.mp4"]:
        if os.path.exists(p) and os.path.getsize(p) > 10000: return p
    return None

# ================= 6. LIVE GLOBAL RSS & STORY CURATION =================
def _extract_rss_image(item):
    for enc in item.findall("enclosure"):
        u = enc.get("url", "")
        if u and enc.get("type", "").startswith("image/"): return u
    for tag in [".//{http://search.yahoo.com/mrss/}content", ".//{http://search.yahoo.com/mrss/}thumbnail"]:
        for m in item.findall(tag):
            u = m.get("url", "")
            if u: return u
    desc = item.findtext("description") or ""
    match = re.search(r'<img[^>]+src=[\"\'](https?://[^\"\']+)[\"\']', desc, re.IGNORECASE)
    if match: return match.group(1)
    return ""

def _clean_summary(raw_html):
    if not raw_html: return ""
    clean = re.sub(r'<[^>]+>', ' ', raw_html)
    clean = re.sub(r'http\S+|www\S+', '', clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = re.sub(r'&[a-z]+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    sentences = re.split(r'[.!?]', clean)
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) >= 25 and not any(k in s_clean.lower() for k in ["read more", "click here", "photo:", "source:", "copyright", "reuters", "ap photo"]):
            return s_clean
    return clean[:140].strip()

def fetch_trending_international_news(category="WORLD", max_items=8):
    urls = NEWS_FEEDS_INTL.get(category, NEWS_FEEDS_INTL["WORLD"])
    headlines, seen = [], set()

    for u in urls:
        if len(headlines) >= max_items: break
        try:
            r = requests.get(u, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                for it in ET.fromstring(r.content).findall(".//item"):
                    raw_t = (it.findtext("title") or "").strip()
                    desc_raw = (it.findtext("description") or "").strip()
                    title = re.sub(r"\s+-\s+[^-]+$", "", raw_t).strip() or raw_t
                    if len(title) < 15 or title.lower() in seen: continue
                    seen.add(title.lower())
                    summary = _clean_summary(desc_raw)

                    loc = "WASHINGTON" if any(w in title.lower() for w in ["us", "biden", "trump", "america"]) else (
                        "GENEVA" if "un" in title.lower() or "united nations" in title.lower() else (
                        "BRUSSELS" if "nato" in title.lower() or "europe" in title.lower() else (
                        "BEIJING" if "china" in title.lower() else (
                        "MOSCOW" if "russia" in title.lower() else "GLOBAL DESK"))))

                    cat_tag = "GEOPOLITICS" if any(w in title.lower() for w in ["treaty", "summit", "president", "diplomacy"]) else (
                        "DEFENSE" if any(w in title.lower() for w in ["military", "missile", "warship", "fighter", "defense"]) else (
                        "WORLD TECH" if any(w in title.lower() for w in ["ai", "space", "satellite", "tech"]) else "WORLD"))

                    headlines.append({
                        "title": title, "summary": summary, "article_url": (it.findtext("link") or "").strip(),
                        "media_url": _extract_rss_image(it),
                        "category_tag": cat_tag,
                        "location_tag": loc,
                    })
                    if len(headlines) >= max_items: break
        except Exception: pass

    rec = get_recommended_topic()
    m = [h for h in headlines if classify_headline_topic(h["title"]) == rec]
    o = [h for h in headlines if classify_headline_topic(h["title"]) != rec]
    if m: headlines = m[:4] + o + m[4:]

    if not headlines:
        headlines = [
            {"title": "United Nations General Assembly Approves Historic Global Security Resolution", "summary": "Member states have voted overwhelmingly in support of strengthened international peacekeeping frameworks.", "category_tag": "GEOPOLITICS", "location_tag": "GENEVA"},
            {"title": "Global Defense Pact Signed Between Allied Powers to Enhance Maritime Security", "summary": "Naval joint operations have been established to protect critical international shipping lanes.", "category_tag": "DEFENSE", "location_tag": "BRUSSELS"},
            {"title": "International Aerospace Consortium Announces New Deep Space Exploration Mission", "summary": "Next-generation lunar satellite arrays have completed primary orbital qualification tests.", "category_tag": "WORLD TECH", "location_tag": "WASHINGTON"},
            {"title": "World Economic Forum Concludes Strategic Summit on Artificial Intelligence Governance", "summary": "Global delegates agreed on strict international safety benchmarks for sovereign AI deployments.", "category_tag": "WORLD TECH", "location_tag": "DAVOS"},
            {"title": "Diplomatic Talks Accelerate Across Regional Powers to Ensure Energy Stability", "summary": "Cross-border energy infrastructure accords were ratified following multilateral deliberations.", "category_tag": "GLOBAL ECONOMY", "location_tag": "GLOBAL DESK"}
        ]
    return headlines[:max_items]

# ================= 7. SPOKEN ENGLISH SCRIPTWRITER & NEURAL VOICE =================
def humanize_english_anchor_speech(title, summary, prefix=""):
    t = re.sub(r'^(BREAKING|EXPLAINER|ANALYSIS|WATCH|UPDATE|EXCLUSIVE|PHOTOS?|VIDEO)\s*[:|-]\s*', '', title or '', flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
    t = re.sub(r'\s*[:|-]?\s*(What to know|Why it matters|What we know|Explained|Read more|See photos).*$', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*:\s*', ', ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    s = re.sub(r'^(EXPLAINER|ANALYSIS|READ)\s*[:|-]\s*', '', summary or '', flags=re.IGNORECASE).strip()
    s = re.sub(r'http\S+|www\S+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    parts = re.split(r'[.!?]', s)
    s_fact = ""
    for p in parts:
        p_clean = p.strip()
        if len(p_clean) >= 25 and not any(k in p_clean.lower() for k in ['read more', 'click here', 'photo:', 'source:', 'copyright', 'reuters', 'ap']):
            s_fact = p_clean
            break
    if not s_fact: s_fact = "International monitoring bodies and correspondents are following developments closely."

    if not t.endswith('.') and not t.endswith(','): t += '.'
    if not s_fact.endswith('.'): s_fact += '.'
    return f"{prefix} {t} {s_fact}".strip() if prefix else f"{t} {s_fact}".strip()

def polish_english_bulletin_with_gemini(headlines):
    if not GEMINI_API_KEY: return headlines
    try:
        items = [f"{i+1}. Headline: {h['title']} | Summary: {h.get('summary', '')}" for i, h in enumerate(headlines)]
        items_text = "\\n".join(items)
        prompt = (
            "You are a world-class International TV News Presenter for Nexora News (broadcasting in the polished, articulate style of BBC World News / CNN International / Bloomberg).\\n"
            "Rewrite each news item into natural, authoritative, spoken English news broadcast anchor speech.\\n"
            "Rules:\\n"
            "1. Deliver an articulate, confident, objective, human news presenter tone.\\n"
            "2. Exactly 2 complete, well-crafted broadcast sentences per story (approx 25 words total).\\n"
            "3. Strip all wire attribution tags, clickbait phrases, or incomplete headlines.\\n"
            "4. Return ONLY a valid JSON list of strings, exactly one per item: ['...', '...']"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt + "\\n\\nHeadlines:\\n" + items_text}]}]}
        r = requests.post(url, json=payload, timeout=12)
        if r.status_code == 200:
            resp_text = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            clean_json = re.search(r'\\[.*\\]', resp_text, re.DOTALL)
            if clean_json:
                scripts = json.loads(clean_json.group(0))
                for i, s in enumerate(scripts):
                    if i < len(headlines) and len(s) > 20:
                        headlines[i]["polished_narration"] = s
                logger.info(f"✨ Gemini humanized {len(scripts)} International English scripts!")
    except Exception as e: logger.warning(f"Gemini English polish notice: {e}")
    return headlines

def synthesize_broadcast_voice(text, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    voice = "en-US-JennyNeural" if gender == "female" else "en-US-GuyNeural"
    clean_speech = text.replace(":", ",").replace("-", ", ").replace("  ", " ")

    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(text=clean_speech, voice=voice, rate="+0%", pitch="-1Hz").save(output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return output_path
    except Exception as e: logger.warning(f"Edge-TTS notice: {e}")

    try:
        from gTTS import gTTS
        gTTS(text=clean_speech, lang="en", slow=False).save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return output_path
    except Exception: pass

    sr = 16000
    dur = max(3.0, min(8.0, len(clean_speech) * 0.08))
    ns = int(dur * sr)
    t = np.linspace(0, dur, ns, endpoint=False)
    pcm = (np.sin(2 * np.pi * 220.0 * t) * 0.35 * (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)) * 32767).astype(np.int16)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm.tobytes())
    return output_path

def create_silence_wav(duration=0.6, output_path="temp/silence.wav", sr=16000):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    ns = int(duration * sr)
    pcm = np.zeros(ns, dtype=np.int16)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm.tobytes())
    return output_path

def _get_audio_duration(path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        return float(subprocess.check_output(cmd).decode().strip())
    except Exception: return 6.0

def generate_pro_broadcast_bed(duration, output_path="temp/broadcast_bed.wav", sr=22050):
    ns = int(duration * sr)
    t = np.linspace(0, duration, ns, endpoint=False)
    bass = np.sin(2 * np.pi * 55.0 * t) * 0.18
    pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t)
    drone = np.sin(2 * np.pi * 110.0 * t) * 0.10 * pulse
    mid = np.sin(2 * np.pi * 220.0 * t) * 0.05 * (0.5 + 0.5 * np.cos(2 * np.pi * 4.0 * t))
    sig = np.clip(bass + drone + mid, -0.85, 0.85)
    pcm = (sig * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm.tobytes())
    return output_path
    # ================= 8. VIDEO RENDERER =================
def build_news_video(script_data, scene_assets, output_path, is_short=True):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    W, H = (1080, 1920) if is_short else (1920, 1080)
    fps = 20

    anchor_vid = find_real_anchor_video(script_data.get("anchor_gender", "female"))
    anchor_engine = RealStudioAnchor(anchor_vid, target_w=(1080 if is_short else 760), target_h=(986 if is_short else 900)) if anchor_vid else None

    silence_pause = create_silence_wav(duration=0.5, output_path="temp/silence_pause.wav")
    silence_outro = create_silence_wav(duration=1.2, output_path="temp/silence_outro.wav")
    concat_list = "temp/concat_audio.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for idx, sc in enumerate(scene_assets):
            f.write(f"file '{os.path.abspath(sc['audio_path'])}'\n")
            if idx < len(scene_assets) - 1:
                f.write(f"file '{os.path.abspath(silence_pause)}'\n")
        f.write(f"file '{os.path.abspath(silence_outro)}'\n")

    merged_voice = "temp/merged_voice.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, merged_voice], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total_aud_dur = _get_audio_duration(merged_voice)
    bgm_path = generate_pro_broadcast_bed(total_aud_dur)

    logo_img = None
    if os.path.exists(LOGO_PATH):
        try:
            logo_raw = Image.open(LOGO_PATH).convert("RGBA")
            logo_img = logo_raw.resize((240, 240) if is_short else (180, 180), Image.Resampling.LANCZOS)
        except Exception: pass

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", merged_voice, "-i", bgm_path,
        "-filter_complex", "[1:a]loudnorm=I=-14:LRA=11:TP=-1.5[vnorm];[2:a]volume=0.18[bgm];[vnorm][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", output_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    global_frame = 0
    ticker_text = f"  ★★★  {CHANNEL_NAME} WORLDWIDE LIVE  ★★★  {TAGLINE}  ★★★  " + "  |  ".join([sc["headline"] for sc in scene_assets]) + "  ★★★  "

    total_required_frames = int((total_aud_dur + 0.5) * fps)
    frame_img = None

    for sc_idx, sc in enumerate(scene_assets):
        dur = sc.get("duration", 6.0)
        dur += (1.2 if sc_idx == len(scene_assets) - 1 else 0.5)
        n_frames = max(1, int(dur * fps))
        story_card = Image.open(sc["image_path"]).convert("RGB")

        for f_idx in range(n_frames):
            frame_img = Image.new("RGB", (W, H), (10, 16, 36))
            anc_frame = anchor_engine.get_frame(global_frame) if anchor_engine else None

            if is_short:
                # Shorts 9:16 Split-Screen Broadcast Layout
                frame_img.paste(story_card.resize((W, 830), Image.Resampling.LANCZOS), (0, 104))
                if anc_frame: frame_img.paste(anc_frame, (0, 934))

                top_bar = Image.new("RGB", (W, 104), (185, 14, 28))
                tb_draw = ImageDraw.Draw(top_bar)
                tb_draw.ellipse([24, 38, 44, 58], fill=(255, 255, 255))
                tb_draw.ellipse([27, 41, 41, 55], fill=(235, 20, 36))
                tb_draw.text((54, 34), f"{CHANNEL_NAME}  |  GLOBAL LIVE", font=_get_font(28, bold=True), fill=(255, 255, 255))
                clock_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
                tb_draw.text((W - 170, 36), clock_str, font=_get_font(26, bold=True), fill=(255, 215, 0))
                frame_img.paste(top_bar, (0, 0))

                mid_strap = Image.new("RGB", (W, 64), (10, 20, 48))
                m_draw = ImageDraw.Draw(mid_strap)
                m_draw.rectangle([0, 0, W, 4], fill=(255, 215, 0))
                m_draw.rectangle([0, 60, W, 64], fill=(255, 215, 0))
                m_draw.text((20, 18), f"⚡ {TAGLINE}", font=_get_font(22, bold=True), fill=(255, 255, 255))
                frame_img.paste(mid_strap, (0, 934))

                bot_bar = Image.new("RGB", (W, 80), (185, 14, 28))
                b_draw = ImageDraw.Draw(bot_bar)
                b_draw.text((200 - (global_frame * 6) % max(1, len(ticker_text) * 16), 24), ticker_text + ticker_text, font=_get_font(24, bold=True), fill=(255, 255, 255))
                b_draw.rectangle([0, 0, 180, 80], fill=(240, 185, 0))
                b_draw.ellipse([20, 32, 34, 46], fill=(210, 16, 30))
                b_draw.text((42, 26), "BREAKING", font=_get_font(22, bold=True), fill=(0, 0, 0))
                frame_img.paste(bot_bar, (0, H - 80))

                if logo_img: frame_img.paste(logo_img, (W - 260, 20), logo_img)
            else:
                # Long 16:9 Virtual Studio Set
                hdr = Image.new("RGB", (W, 70), (12, 22, 54))
                h_draw = ImageDraw.Draw(hdr)
                h_draw.ellipse([26, 26, 42, 42], fill=(235, 20, 36))
                h_draw.text((50, 20), f"{CHANNEL_NAME} WORLDWIDE LIVE  |  {TAGLINE}", font=_get_font(22, bold=True), fill=(255, 215, 0))
                clock_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                h_draw.text((W - 190, 20), clock_str, font=_get_font(20, bold=True), fill=(255, 255, 255))
                frame_img.paste(hdr, (0, 0))

                if anc_frame: frame_img.paste(anc_frame, (20, 90))
                frame_img.paste(story_card.resize((1100, 740), Image.Resampling.LANCZOS), (790, 110))
                if logo_img: frame_img.paste(logo_img, (30, H - 280), logo_img)

                tick_bar = Image.new("RGB", (W, 76), (185, 14, 28))
                t_draw = ImageDraw.Draw(tick_bar)
                t_draw.text((180 - (global_frame * 6) % max(1, len(ticker_text) * 16), 24), ticker_text + ticker_text, font=_get_font(24, bold=True), fill=(255, 255, 255))
                t_draw.rectangle([0, 0, 170, 76], fill=(240, 185, 0))
                t_draw.text((16, 24), "🔴 WORLD NEWS", font=_get_font(20, bold=True), fill=(0, 0, 0))
                frame_img.paste(tick_bar, (0, H - 76))

            proc.stdin.write(frame_img.tobytes())
            global_frame += 1

    while global_frame < total_required_frames:
        proc.stdin.write(frame_img.tobytes())
        global_frame += 1

    proc.stdin.close()
    proc.wait()
    logger.info(f"🎬 Video complete: {output_path} ({os.path.getsize(output_path)/(1024*1024):.2f} MB)")
    return output_path

# ================= 9. THUMBNAIL & YOUTUBE ENGINE =================
def generate_broadcast_thumbnail(headline, photo_path, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    TW, TH = 1280, 720
    base = Image.new("RGB", (TW, TH), (12, 22, 54))

    photo_w = 800
    lead_img_path = "temp/lead_raw_photo.jpg" if os.path.exists("temp/lead_raw_photo.jpg") else photo_path
    if lead_img_path and os.path.exists(lead_img_path):
        try:
            pimg = _validate_image(open(lead_img_path, "rb").read(), photo_w, TH)
            base.paste(pimg, (TW - photo_w, 0))
        except Exception: pass
    else:
        backdrop = Image.new("RGB", (photo_w, TH), (14, 26, 68))
        bdraw = ImageDraw.Draw(backdrop)
        for y in range(TH):
            r = int(14 + (y / TH) * 20)
            g = int(24 + (y / TH) * 20)
            b = int(60 + (y / TH) * 50)
            bdraw.line([(0, y), (photo_w, y)], fill=(r, g, b))
        for r_size in [120, 240, 360, 480, 600]:
            bdraw.ellipse([400 - r_size, TH // 2 - r_size, 400 + r_size, TH // 2 + r_size], outline=(35, 60, 130), width=2)
        for gx in range(0, photo_w, 100): bdraw.line([(gx, 0), (gx, TH)], fill=(28, 48, 105), width=1)
        for gy in range(0, TH, 100): bdraw.line([(0, gy), (photo_w, gy)], fill=(28, 48, 105), width=1)
        base.paste(backdrop, (TW - photo_w, 0))

    anc_vid = find_real_anchor_video(gender)
    if anc_vid:
        try:
            anc = RealStudioAnchor(anc_vid, target_w=520, target_h=TH)
            if anc.total > 0: base.paste(anc.get_frame(30), (0, 0))
        except Exception: pass

    overlay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for x in range(440, 560):
        alpha = int(((560 - x) / 120.0) * 160)
        odraw.line([(x, 0), (x, TH)], fill=(12, 22, 54, alpha))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(base)
    draw.rectangle([0, 0, TW - 1, TH - 1], outline=(220, 20, 36), width=6)
    draw.rectangle([6, 6, TW - 7, TH - 7], outline=(255, 215, 0), width=2)

    # Top Left: Live Nexora News
    draw.rounded_rectangle([30, 24, 460, 78], radius=8, fill=(210, 16, 30), outline=(255, 215, 0), width=2)
    draw.ellipse([46, 42, 64, 60], fill=(255, 255, 255))
    draw.ellipse([50, 46, 60, 56], fill=(235, 20, 36))
    draw.text((78, 36), "NEXORA NEWS  |  WORLD LIVE", font=_get_font(24, bold=True), fill=(255, 255, 255))

    if os.path.exists(LOGO_PATH):
        try:
            logo_raw = Image.open(LOGO_PATH).convert("RGBA").resize((140, 140), Image.Resampling.LANCZOS)
            base.paste(logo_raw, (TW - 170, 24), logo_raw)
        except Exception: pass

    # Lower Third Headline Box (High-CTR Bold Text)
    draw.rectangle([20, TH - 220, TW - 20, TH - 20], fill=(8, 14, 28))
    draw.rectangle([20, TH - 224, TW - 20, TH - 218], fill=(255, 215, 0))

    clean_hl = re.sub(r'^(BREAKING|EXPLAINER|ANALYSIS|WATCH|UPDATE|EXCLUSIVE|PHOTOS?|VIDEO)\s*[:|-]\s*', '', headline or '', flags=re.IGNORECASE).strip()
    clean_hl = re.sub(r'\s*-\s*[^-]+$', '', clean_hl).strip()
    clean_hl = clean_hl.upper()

    lines = wrap_text_to_width(draw, clean_hl, _get_font(42, bold=True), TW - 80, max_lines=2)
    if lines:
        draw.text((44, TH - 200), lines[0], font=_get_font(42, bold=True), fill=(0, 0, 0))
        draw.text((40, TH - 202), lines[0], font=_get_font(42, bold=True), fill=(255, 235, 60))
    if len(lines) > 1:
        draw.text((44, TH - 132), lines[1], font=_get_font(38, bold=True), fill=(0, 0, 0))
        draw.text((40, TH - 134), lines[1], font=_get_font(38, bold=True), fill=(255, 255, 255))

    base.save(output_path, "JPEG", quality=95)
    return output_path

def _get_youtube_token():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN): return None
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={"client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SECRET, "refresh_token": YT_REFRESH_TOKEN, "grant_type": "refresh_token"}, timeout=20)
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception: return None

def _sanitize_title(title, is_short=True):
    t = re.sub(r'\s+', ' ', (title or "").strip())
    if is_short and "#Shorts" not in t: t = f"{t} #Shorts"
    b = t.encode("utf-8")
    return b[:95].decode("utf-8", errors="ignore").rstrip() if len(b) > 95 else t

def sync_youtube_analytics():
    token = _get_youtube_token()
    if not token: return load_topic_analytics()
    adata = load_topic_analytics()
    h = {"Authorization": f"Bearer {token}"}
    try:
        cr = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet,statistics,contentDetails", "mine": "true"}, headers=h, timeout=15)
        if cr.status_code == 200:
            items = cr.json().get("items", [])
            if items:
                st = items[0].get("statistics", {})
                up_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                adata["channel_stats"] = {"subscribers": int(st.get("subscriberCount", 0)), "total_views": int(st.get("viewCount", 0)), "video_count": int(st.get("videoCount", 0))}
                logger.info(f"📊 LIVE YOUTUBE ({CHANNEL_NAME}): Subs: {adata['channel_stats']['subscribers']:,} | Views: {adata['channel_stats']['total_views']:,}")
                if up_id:
                    pr = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params={"part": "contentDetails", "playlistId": up_id, "maxResults": "25"}, headers=h, timeout=15)
                    if pr.status_code == 200:
                        vids = [pi.get("contentDetails", {}).get("videoId") for pi in pr.json().get("items", []) if pi.get("contentDetails", {}).get("videoId")]
                        if vids:
                            vr = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,statistics", "id": ",".join(vids[:50])}, headers=h, timeout=15)
                            if vr.status_code == 200:
                                t_stats = {}
                                for v in vr.json().get("items", []):
                                    top = classify_headline_topic(v.get("snippet", {}).get("title", ""))
                                    t_stats.setdefault(top, {"count": 0, "views": 0})
                                    t_stats[top]["count"] += 1
                                    t_stats[top]["views"] += int(v.get("statistics", {}).get("viewCount", 0))
                                if t_stats:
                                    adata["recommended_topic"] = max(t_stats.items(), key=lambda x: x[1]["views"] / max(1, x[1]["count"]))[0]
                                    logger.info(f"🎯 [WINNING TOPIC]: '{adata['recommended_topic']}' has highest average views!")
        save_topic_analytics(adata)
    except Exception as e: logger.warning(f"Analytics sync warning: {e}")
    return adata

def upload_to_youtube(video_path, title, description, tags, thumb_path=None, is_short=True):
    report_file = "output/YOUTUBE_UPLOAD_REPORT.txt"
    os.makedirs("output", exist_ok=True)
    token = _get_youtube_token()
    if not token:
        msg = f"[{datetime.now().isoformat()}] ❌ YOUTUBE AUTH FAILED: Check YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN secrets in GitHub."
        logger.error(msg)
        with open(report_file, "a", encoding="utf-8") as rf: rf.write(msg + "\n")
        return None

    safe_t = _sanitize_title(title, is_short=is_short)
    fsz = os.path.getsize(video_path)
    body = {"snippet": {"title": safe_t, "description": description[:4500], "tags": tags[:25], "categoryId": "25", "defaultLanguage": "en"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    try:
        init_r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": str(fsz), "X-Upload-Content-Type": "video/mp4"}, json=body, timeout=30)
        up_url = init_r.headers.get("Location")
        if not up_url:
            err_text = init_r.text[:300]
            msg = f"[{datetime.now().isoformat()}] ❌ YOUTUBE UPLOAD INIT FAILED (HTTP {init_r.status_code}): {err_text}"
            logger.error(msg)
            with open(report_file, "a", encoding="utf-8") as rf: rf.write(msg + "\n")
            return None

        vid_id = None
        with open(video_path, "rb") as vf:
            uploaded = 0
            while uploaded < fsz:
                chunk = vf.read(8 * 1024 * 1024)
                if not chunk: break
                pr = requests.put(up_url, headers={"Authorization": f"Bearer {token}", "Content-Length": str(len(chunk)), "Content-Type": "video/mp4", "Content-Range": f"bytes {uploaded}-{uploaded + len(chunk) - 1}/{fsz}"}, data=chunk, timeout=180)
                uploaded += len(chunk)
                if pr.status_code in (200, 201):
                    vid_id = pr.json().get("id")
                    break
                elif pr.status_code != 308:
                    msg = f"[{datetime.now().isoformat()}] ❌ CHUNK UPLOAD FAILED (HTTP {pr.status_code}): {pr.text[:300]}"
                    logger.error(msg)
                    with open(report_file, "a", encoding="utf-8") as rf: rf.write(msg + "\n")
                    break

        if vid_id:
            v_url = f"https://youtu.be/{vid_id}"
            logger.info(f"🎉 LIVE ON YOUTUBE: {v_url}")
            with open(report_file, "a", encoding="utf-8") as rf:
                rf.write(f"[{datetime.now().isoformat()}] ✅ SUCCESS: {v_url} | Title: {safe_t}\n")

            if thumb_path and os.path.exists(thumb_path) and not is_short:
                try:
                    tr = requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}", headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}, data=open(thumb_path, "rb").read(), timeout=30)
                    if tr.status_code in (200, 201):
                        logger.info(f"🖼️ Thumbnail uploaded successfully for {vid_id}")
                    else:
                        logger.warning(f"⚠️ Thumbnail upload warning HTTP {tr.status_code}: {tr.text[:200]}")
                except Exception as te:
                    logger.warning(f"Thumbnail upload exception: {te}")
            return vid_id
    except Exception as e:
        msg = f"[{datetime.now().isoformat()}] ❌ YOUTUBE UPLOAD EXCEPTION: {e}"
        logger.error(msg)
        with open(report_file, "a", encoding="utf-8") as rf: rf.write(msg + "\n")
    return None

# ================= 10. EPISODE ORCHESTRATOR =================
def produce_news_episode(category="WORLD", is_short=True, edition="auto", anchor_gender=None, skip_upload=False):
    ed = get_current_edition() if edition == "auto" else edition.upper()
    cfg = EDITION_CONFIGS.get(ed, EDITION_CONFIGS["MORNING"])
    headlines = fetch_trending_international_news(category=("WORLD" if category == "AUTO" else category), max_items=(5 if is_short else cfg["target_count"]))
    gender = anchor_gender or ("female" if random.random() < 0.5 else "male")

    lead_t = re.sub(r'^(BREAKING|EXPLAINER|ANALYSIS|WATCH|UPDATE|EXCLUSIVE|PHOTOS?|VIDEO)\s*[:|-]\s*', '', headlines[0]["title"], flags=re.IGNORECASE).strip() if headlines else "Global Strategic Developments"
    lead_t = re.sub(r'\s*-\s*[^-]+$', '', lead_t).strip()
    lead_short = lead_t[:45].strip() + ("..." if len(lead_t) > 45 else "")

    if is_short:
        video_title = f"🚨 Breaking: {lead_short} | Top 5 World News #Shorts #WorldNews #NexoraNews"
    else:
        video_title = f"🔴 {lead_short} | {cfg['title_prefix']} | {CHANNEL_NAME}"

    script = {"title": video_title, "anchor_gender": gender}
    assets, lead_photo = [], None

    # ===== DEDICATED INTRO SCENE FOR LONG BULLETINS =====
    if not is_short:
        intro_img = "temp/scene_intro.jpg"
        intro_aud = "temp/voice_intro.mp3"
        create_broadcast_story_card(
            intro_img,
            headline=f"{cfg['title_prefix']} | {CHANNEL_NAME}",
            counter="LIVE INTRO",
            category="SPECIAL BULLETIN",
            location="GLOBAL HEADQUARTERS",
            bulletin=cfg["bulletin_label"],
            is_short=False,
        )
        intro_narration = (
            f"Welcome to {CHANNEL_NAME}—{TAGLINE}. "
            f"Bringing you continuous global coverage across international geopolitics, diplomacy, and global technology. "
            f"Here are today's top international developments."
        )
        synthesize_broadcast_voice(intro_narration, intro_aud, gender=gender)
        assets.append({
            "scene_id": 0, "image_path": intro_img, "audio_path": intro_aud,
            "headline": f"Global Briefing: {CHANNEL_NAME}", "duration": _get_audio_duration(intro_aud),
        })

    # ===== MAIN STORIES WITH ARTICULATE SPOKEN ENGLISH NARRATIVE =====
    intro_prefixes = [
        "In our top international story,",
        "Turning now to global diplomacy,",
        "In major defense and strategic developments,",
        "Looking at international technology and markets,",
        "And in other critical global news,",
        "In our sixth top development,",
        "Moving to international security,",
        "In major aerospace and technological strides,"
    ]

    headlines = polish_english_bulletin_with_gemini(headlines)

    for idx, h in enumerate(headlines):
        sid = idx + 1
        img_p, aud_p = f"temp/scene_{sid}.jpg", f"temp/voice_{sid}.mp3"
        counter = f"STORY {sid} OF 5" if is_short else f"STORY {sid} OF {len(headlines)}"
        bulletin_tag = "WORLD 5" if is_short else cfg["bulletin_label"]

        clean_title = re.sub(r'^(BREAKING|EXPLAINER|ANALYSIS|WATCH|UPDATE|EXCLUSIVE|PHOTOS?|VIDEO)\s*[:|-]\s*', '', h["title"], flags=re.IGNORECASE).strip()
        clean_title = re.sub(r'\s*-\s*[^-]+$', '', clean_title).strip()

        download_scene_image(img_p, prompt=clean_title, rss_url=h.get("media_url", ""), article_url=h.get("article_url", ""), headline=clean_title, counter=counter, category=h.get("category_tag", "WORLD"), location=h.get("location_tag", "GLOBAL DESK"), bulletin=bulletin_tag, is_short=is_short, scene_idx=idx)
        if idx == 0 and os.path.exists(img_p): lead_photo = img_p

        prefix = intro_prefixes[idx % len(intro_prefixes)]
        if h.get("polished_narration"):
            narration = f"{prefix} {h['polished_narration']}"
        else:
            narration = humanize_english_anchor_speech(h["title"], h.get("summary", ""), prefix=prefix)

        if is_short and idx == len(headlines) - 1:
            narration += f" For continuous 24/7 global news coverage, subscribe to {CHANNEL_NAME}."

        synthesize_broadcast_voice(narration, aud_p, gender=gender)
        assets.append({"scene_id": sid, "image_path": img_p, "audio_path": aud_p, "headline": clean_title, "duration": _get_audio_duration(aud_p)})

    # ===== DEDICATED OUTRO SCENE FOR LONG BULLETINS =====
    if not is_short:
        outro_img = "temp/scene_outro.jpg"
        outro_aud = "temp/voice_outro.mp3"
        create_broadcast_story_card(
            outro_img,
            headline=f"Subscribe to {CHANNEL_NAME} | Global Updates",
            counter="LIVE OUTRO",
            category="NETWORK UPDATE",
            location="GLOBAL HEADQUARTERS",
            bulletin="SUBSCRIBE NOW",
            is_short=False,
        )
        outro_narration = (
            f"Those are the top international headlines from the {CHANNEL_NAME} global newsroom. "
            f"For verified 24/7 world coverage across defense, geopolitics, and technology, subscribe to {CHANNEL_NAME} and enable notifications. "
            f"Thank you for watching."
        )
        synthesize_broadcast_voice(outro_narration, outro_aud, gender=gender)
        assets.append({
            "scene_id": len(headlines) + 1, "image_path": outro_img, "audio_path": outro_aud,
            "headline": f"Subscribe to {CHANNEL_NAME}", "duration": _get_audio_duration(outro_aud),
        })

    out = "final_short.mp4" if is_short else "final_long.mp4"
    build_news_video(script, assets, out, is_short=is_short)
    thumb = "temp/broadcast_thumb.jpg"
    if not is_short: generate_broadcast_thumbnail(headlines[0]["title"] if headlines else "Top International News", lead_photo, thumb, gender=gender)

    if not skip_upload:
        time_cursor = 0.0
        chapters = []
        for sc in assets:
            mins, secs = int(time_cursor // 60), int(time_cursor % 60)
            chapters.append(f"{mins:02d}:{secs:02d} - {sc['headline']}")
            time_cursor += sc.get("duration", 8.0) + 0.5

        desc = (
            f"{script['title']}\n\n"
            f"📺 {CHANNEL_NAME} (Worldwide)\n"
            f"⚡ {TAGLINE}\n"
            f"🌐 {SUB_TAGLINE}\n\n"
            f"📌 In This Global Broadcast (Chapters & Timestamps):\n"
            + "\n".join(chapters)
            + f"\n\n🌐 About Nexora News:\n"
            f"Nexora News is an autonomous AI-powered global news network delivering verified, independent coverage across international diplomacy, geopolitics, defense, and frontier technology.\n\n"
            f"🔔 Subscribe to Nexora News for continuous 24/7 international updates and ring the notification bell!\n\n"
            f"#NexoraNews #WorldNews #BreakingNews #GlobalAffairs #Geopolitics #InternationalNews #DefenseNews #Shorts"
        )
        upload_tags = [CHANNEL_NAME, "Nexora News World", "World News", "Breaking News", "International News", "Global Affairs", "Geopolitics", "Defense News", "World News Today", "Daily World News", "Global News Live", "BBC World News", "CNN", "Technology News", "United Nations"]
        upload_to_youtube(out, script["title"], desc, upload_tags, thumb_path=thumb, is_short=is_short)
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--type", default="both")
    p.add_argument("--edition", default="auto")
    p.add_argument("--category", default="WORLD")
    p.add_argument("--anchor", default="auto")
    p.add_argument("--skip-upload", action="store_true")
    p.add_argument("--check-youtube", action="store_true")
    args = p.parse_args()

    if args.check_youtube:
        tok = _get_youtube_token()
        if tok: logger.info("✅ YouTube OAuth2 Access Token Verified!"); sys.exit(0)
        logger.error("❌ YouTube Auth Check Failed"); sys.exit(1)

    if not args.skip_upload: sync_youtube_analytics()
    vtype = (args.type or "both").strip().lower()
    if vtype not in ("short", "long", "both"): vtype = "both"
    vedition = (args.edition or "auto").strip().lower()
    if vedition not in ("auto", "morning", "afternoon", "evening"): vedition = "auto"
    vcat = (args.category or "WORLD").strip().upper()
    vanc = None if (not args.anchor or args.anchor == "auto") else args.anchor.strip().lower()

    if vtype in ("short", "both"): produce_news_episode(category=vcat, is_short=True, edition=vedition, anchor_gender=vanc, skip_upload=args.skip_upload)
    if vtype in ("long", "both"): produce_news_episode(category=vcat, is_short=False, edition=vedition, anchor_gender=vanc, skip_upload=args.skip_upload)

if __name__ == "__main__":
    main()
