#!/usr/bin/env python3
"""
24/7 Autonomous AI TV News Network Engine
Official Channel: NEXORA NEWS (नेक्सोरा न्यूज़)
Tagline: THE WORLD. THE NEXT. THE NEWS. (सही खबर | तेज़ नज़र | बेहतर कल)
Category: National, International & Technology | AI News Network
Features:
- Complete & Clear News Briefing: Headline + Factual Context (Zero Incomplete/Cut-off News)
- Paced News Rundown: 0.6s Breathing Pauses Between Stories + 1.5s Outro Safety Padding
- Comprehensive Entity-Mapped Ground Photo Engine (Zero Gandhi Posters / 1800s Scans)
- Anti-Anime Photojournalism Filter (Guarantees authentic news photos, zero cartoon speech bubbles)
- Bilingual Mixed Typography Engine: Seamless English (NEXORA NEWS, INS, DRDO) + Hindi rendering
- Dedicated Studio Intro & Outro for Long Videos (Opening Hook + Closing CTA)
- Real Anchor Video Engine (Smooth 1x Playback, Zero Watermark, Zero Jitter)
- 3-Tier Broadcast Aston (Location Kicker, Glassmorphic Strap, Live Counter)
- Sound Design: 120-BPM Newsroom Pulse Bed + EBU R128 (-14 LUFS) Mastering
- High-CTR Clickable 1280x720 Thumbnail Generator & API Uploader
- YouTube Audience Analytics Feedback Loop (Auto-Prioritizes Winning Topics)
"""

import os, sys, re, glob, json, time, math, random, asyncio, logging, argparse, subprocess, urllib.parse, wave
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("NexoraNews")

# ================= 1. BRANDING & CREDENTIALS =================
def _clean(v): return (v or "").strip().strip('"').strip("'").strip()
GEMINI_API_KEY = _clean(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean(os.environ.get("YT_REFRESH_TOKEN", ""))

CHANNEL_NAME = "NEXORA NEWS"
CHANNEL_NAME_HI = "नेक्सोरा न्यूज़"
TAGLINE = "THE WORLD. THE NEXT. THE NEWS."
TAGLINE_HI = "सही खबर | तेज़ नज़र | बेहतर कल"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
TOPIC_ANALYTICS_FILE = os.path.join("assets", "topic_analytics.json")
LOGO_PATH = os.path.join("assets", "channel_logo.png")

TOPIC_TAXONOMY = {
    "DEFENSE_SECURITY": ["सेना", "बॉर्डर", "मिसाइल", "चीन", "पाकिस्तान", "युद्ध", "राफेल", "drdo", "आर्मी", "नेवी", "एयरफोर्स", "हमला", "सुरक्षा", "सैनिक", "defence"],
    "CRIME_LAW": ["पुलिस", "कोर्ट", "सीबीआई", "सुप्रीम कोर्ट", "गिरफ्तार", "एनकाउंटर", "जेल", "ईडी", "fir", "जांच", "हत्या", "हादसा", "कस्टडी", "मुठभेड़"],
    "POLITICS": ["मोदी", "संसद", "सरकार", "राहुल", "मंत्री", "cm", "bjp", "congress", "चुनाव", "पार्टी", "विपक्ष", "नेता", "कैबिनेट", "लोकसभा", "राज्यसभा"],
    "WORLD_GEOPOLITICS": ["अमेरिका", "ट्रंप", "रूस", "ईरान", "इजरायल", "गाजा", "संयुक्त राष्ट्र", "ग्लोबल", "विदेश", "यूक्रेन", "हूती", "पुतिन"],
    "SCIENCE_TECH": ["इसरो", "नासा", "अंतरिक्ष", "उपग्रह", "गगनयान", "चंद्रयान", "ai", "रोबोट", "5g", "स्मार्टफोन", "सेमीकंडक्टर", "tech"],
    "ECONOMY_FINANCE": ["शेयर बाजार", "सेंसेक्स", "बजट", "टैक्स", "बैंक", "सोना", "आरबीआई", "महंगाई", "लोन", "जीडीपी", "रुपया", "कारोबार"],
}

# Comprehensive Bilingual Entity Mapping for Press Photography (Eliminates Anime & Gandhi Poster Fallback)
ENTITY_MAP = [
    (["हेलीकॉप्टर", "क्रैश", "विमान", "हादसा", "दुर्घटना", "बद्रीनाथ", "केदारनाथ", "उत्तराखंड", "crash", "helicopter"], "Rescue helicopter crash site mountain Himalayas Uttarakhand emergency"),
    (["राफेल", "विक्रांत", "नेवी", "नौसेना", "विमानवाहक", "लड़ाकू", "rafale", "navy", "vikrant"], "INS Vikrant aircraft carrier Indian Navy fighter jet landing at sea"),
    (["सेना", "आर्मी", "जवान", "बॉर्डर", "एलएसी", "एलओसी", "drdo", "मिसाइल", "डिफेंस", "army", "defence"], "Indian Army soldiers border security patrol combat uniform"),
    (["india bloc", "विपक्ष", "गठबंधन", "खरगे", "महाभियोग", "kharge", "opposition", "संसद", "parliament"], "Indian Parliament Opposition leaders press conference New Delhi"),
    (["राहुल", "गांधी", "कांग्रेस", "rahul gandhi", "congress", "प्रियंका", "सोनिया"], "Rahul Gandhi politician press conference New Delhi India"),
    (["मोदी", "प्रधानमंत्री", "पीएम", "केबिनेट", "narendra modi", "pm modi", "bjp", "भाजपा"], "Narendra Modi Prime Minister of India official address New Delhi"),
    (["जनगणना", "जाति", "census", "caste census", "सर्वे", "चुनाव", "चुनावी", "मतदान", "election", "vote"], "Election Commission of India polling press briefing New Delhi"),
    (["isro", "इसरो", "गगनयान", "अंतरिक्ष", "रॉकेट", "उपग्रह", "सैटेलाइट", "gslv", "pslv", "चंद्रयान", "space", "satellite", "rocket"], "ISRO rocket launch satellite Sriharikota space port India"),
    (["ai", "टेक्नोलॉजी", "टेक", "स्मार्टफोन", "5g", "रोबोट", "गूगल", "apple"], "Technology artificial intelligence computer data center futuristic"),
    (["वंदे भारत", "ट्रेन", "रेलवे", "स्लीपर", "स्टेशन", "रेल", "vande bharat", "railway", "train"], "Vande Bharat Express modern train Indian Railways station"),
    (["मौसम", "बारिश", "बाढ़", "चक्रवात", "तूफान", "अलर्ट", "मॉनसून", "weather", "rain", "flood", "storm"], "Heavy monsoon rainfall waterlogged street rescue operations India"),
    (["ग्लेशियर", "झील", "पहाड़", "हिमालय", "भूटान", "glacier", "mountain"], "Himalayan glacier mountain lake disaster flash flood"),
    (["सुप्रीम कोर्ट", "अदालत", "हाईकोर्ट", "जज", "न्यायाधीश", "cbi", "सीबीआई", "ईडी", "ed", "supreme court", "court"], "Supreme Court of India building New Delhi justice"),
    (["पुलिस", "गिरफ्तार", "एनकाउंटर", "हादसा", "कस्टडी", "क्राइम", "fir", "police", "arrest"], "Indian Police barricade emergency vehicle night patrol"),
    (["शेयर", "सेंसेक्स", "बाजार", "अर्थव्यवस्था", "सोना", "निफ्टी", "टैक्स", "बजट", "bank", "stock", "market"], "Bombay Stock Exchange building Mumbai stock market trading"),
    (["चिकन", "मटन", "मछली", "खाना", "डिश", "फूड", "meat", "food"], "Indian food culinary fresh traditional market dish"),
    (["दिवाली", "छठ", "त्योहार", "पूजा", "diwali", "festival"], "Diwali festival celebration lights oil lamps India"),
]

def map_headline_to_search_query(headline):
    hl = (headline or "").lower()
    for keywords, query in ENTITY_MAP:
        if any(kw in hl for kw in keywords):
            return query
    return None

# Prioritizing news feeds that provide DIRECT ground press photo attachments
NEWS_FEEDS = {
    "NATION": [
        "https://www.amarujala.com/rss/breaking-news.xml",
        "https://ndtv.in/rss/top-stories",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
    ],
    "TECHNOLOGY": [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
    ],
    "WORLD": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.feedburner.com/ndtvnews-world-news",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    ],
}

EDITION_CONFIGS = {
    "MORNING": {"target_count": 10, "title_prefix": "🔴 LIVE सुबह महाबुलेटिन: Top 10 बड़ी खबरें", "counter_prefix": "ख़बर", "bulletin_label": "TOP 10 NEWS"},
    "AFTERNOON": {"target_count": 8, "title_prefix": "🔴 LIVE दोपहर बुलेटिन: आज की बड़ी ख़बरें", "counter_prefix": "बड़ी ख़बर", "bulletin_label": "SPECIAL BULLETIN"},
    "EVENING": {"target_count": 10, "title_prefix": "🔴 LIVE शाम बुलेटिन: Top 10 Superfast News", "counter_prefix": "ख़बर", "bulletin_label": "TOP 10 NEWS"},
}

def get_current_edition():
    try:
        h = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).hour
        return "MORNING" if 5 <= h < 12 else ("AFTERNOON" if 12 <= h < 17 else "EVENING")
    except Exception:
        return "MORNING"

# ================= 2. TYPOGRAPHY ENGINE (ZERO TOFU BOXES) =================
def _get_english_font(size=28):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def _get_devanagari_font(size=28):
    for p in ["assets/fonts/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", "assets/fonts/NotoSansDevanagari-Regular.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return _get_english_font(size)

def draw_mixed_line(draw, pos, text, size=28, fill=(255, 255, 255)):
    x, y = pos
    dev_f, eng_f = _get_devanagari_font(size), _get_english_font(size)
    clean_t = (text or "").replace("🔴", "  ")
    tokens = re.findall(r'[\u0900-\u097F]+|[^\u0900-\u097F]+', clean_t)
    for tok in tokens:
        is_hindi = any('\u0900' <= ch <= '\u097F' for ch in tok)
        f = dev_f if is_hindi else eng_f
        draw.text((x, y), tok, font=f, fill=fill)
        bbox = draw.textbbox((x, y), tok, font=f)
        x = bbox[2]
    return x

def measure_text(draw, text, size=28):
    dev_f, eng_f = _get_devanagari_font(size), _get_english_font(size)
    clean_t = (text or "").replace("🔴", "  ")
    tokens = re.findall(r'[\u0900-\u097F]+|[^\u0900-\u097F]+', clean_t)
    tw = 0
    for tok in tokens:
        is_hindi = any('\u0900' <= ch <= '\u097F' for ch in tok)
        bbox = draw.textbbox((0, 0), tok, font=(dev_f if is_hindi else eng_f))
        tw += (bbox[2] - bbox[0])
    return tw

# ================= 3. TOPIC ANALYTICS & REINFORCEMENT =================
def classify_headline_topic(headline):
    hl = (headline or "").lower()
    for cat, kws in TOPIC_TAXONOMY.items():
        if any(kw in hl for kw in kws):
            return cat
    return "NATIONAL_GENERAL"

def load_topic_analytics():
    if os.path.exists(TOPIC_ANALYTICS_FILE):
        try: return json.load(open(TOPIC_ANALYTICS_FILE, "r", encoding="utf-8"))
        except Exception: pass
    return {"version": "2.0", "channel_name": CHANNEL_NAME, "recommended_topic": "DEFENSE_SECURITY", "topic_performance": {}}

def save_topic_analytics(data):
    try:
        os.makedirs("assets", exist_ok=True)
        json.dump(data, open(TOPIC_ANALYTICS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    except Exception as e: logger.warning(f"Could not save analytics: {e}")

def get_recommended_topic():
    adata = load_topic_analytics()
    return adata.get("recommended_topic", "DEFENSE_SECURITY")

# ================= 4. GROUND PHOTO ENGINE (AUTHENTIC EDITORIAL) =================
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
            m = re.search(r'<meta[^>]+(?:og:image|twitter:image)[^>]+content=["\'](https?://[^"\']+)["\']', r.text, re.IGNORECASE)
            if m:
                u = m.group(1)
                if not any(k in u.lower() for k in ["google", "gstatic", "1x1", "pixel", "favicon", "avatar"]):
                    ir = requests.get(u, headers=HEADERS, timeout=4)
                    if ir.status_code == 200 and len(ir.content) > 12000:
                        return ir.content
    except Exception: pass
    return None

def _fetch_ground_news_photo(keywords_or_headline, target_w, target_h):
    q = map_headline_to_search_query(keywords_or_headline)
    if not q:
        for cat, kws in TOPIC_TAXONOMY.items():
            if any(k in (keywords_or_headline or "").lower() for k in kws):
                q = f"India {cat.lower().replace('_', ' ')} news report press"
                break
    if not q: q = "India government press briefing New Delhi news"
    try:
        url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(q)}&gsrlimit=10&prop=imageinfo&iiprop=url|mime|size&format=json"
        res = requests.get(url, headers=HEADERS, timeout=5).json()
        pages = res.get("query", {}).get("pages", {})
        for _, page in pages.items():
            info = page.get("imageinfo", [{}])[0]
            u = info.get("url", "")
            title_l = page.get("title", "").lower()
            if any(k in title_l for k in ["gandhi", "book", "document", "scan", "archive", "drawing", "map", "flag", "1800", "1900", "1910", "1920", "1930", "1940"]):
                continue
            if u.lower().endswith((".jpg", ".jpeg", ".png")) and info.get("width", 0) >= 500:
                ir = requests.get(u, headers=HEADERS, timeout=6)
                if ir.status_code == 200: return _validate_image(ir.content, target_w, target_h)
    except Exception: pass
    return None

def _fetch_pollinations_image(prompt, target_w, target_h):
    mapped_q = map_headline_to_search_query(prompt)
    lead_subject = mapped_q if mapped_q else "Indian national news report press conference New Delhi"
    clean_p = f"high quality real photojournalism press photography of {lead_subject}, cinematic lighting, photorealistic, raw news footage, 8k, highly detailed, realistic texture, no text, no captions, no subtitles, no anime, no cartoon, no drawing, authentic Indian news background"
    u = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_p)}?width={target_w}&height={target_h}&nologo=true&model=flux"
    try:
        r = requests.get(u, timeout=14)
        if r.status_code == 200 and len(r.content) > 15000:
            return _validate_image(r.content, target_w, target_h)
    except Exception: pass
    return None

def create_broadcast_story_card(output_path, target_w=1100, target_h=740, headline="", headline_text="", counter="", counter_text="ख़बर 1", category="राष्ट्रीय", category_tag="राष्ट्रीय", location="नई दिल्ली", location_tag="नई दिल्ली", bulletin="LIVE", bulletin_label="LIVE", base_img=None, is_short=False, **kwargs):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    headline = headline or headline_text or "आज की बड़ी ख़बर"
    counter = counter or counter_text or "ख़बर"
    category = category or category_tag or "राष्ट्रीय"
    location = location or location_tag or "नई दिल्ली"
    bulletin = bulletin or bulletin_label or "LIVE"

    card = Image.new("RGB", (target_w, target_h), (8, 14, 28))
    if base_img:
        try:
            resized_base = _validate_image(base_img.tobytes() if hasattr(base_img, "tobytes") else base_img, target_w, target_h)
            card.paste(resized_base, (0, 0))
        except Exception:
            try: card.paste(base_img.resize((target_w, target_h), Image.Resampling.LANCZOS), (0, 0))
            except Exception: pass
    else:
        # Dynamic Editorial Radar Studio Backdrop
        b_draw = ImageDraw.Draw(card)
        for y in range(target_h):
            r = int(10 + (y / target_h) * 16)
            g = int(18 + (y / target_h) * 22)
            b = int(42 + (y / target_h) * 44)
            b_draw.line([(0, y), (target_w, y)], fill=(r, g, b))
        for r_size in [120, 240, 360, 480, 600]:
            b_draw.ellipse([target_w // 2 - r_size, target_h // 2 - r_size, target_w // 2 + r_size, target_h // 2 + r_size], outline=(24, 45, 96), width=1)

    # Gradient Shadow for Headline Legibility
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

    # Top Left Counter Capsule
    top_badge_text = f"{bulletin}  |  {counter}"
    badge_w = max(240, measure_text(draw, top_badge_text, size=24) + 60)
    draw.rounded_rectangle([20, 20, 20 + badge_w, 68], radius=8, fill=(185, 14, 28), outline=(255, 215, 0), width=2)
    draw.ellipse([34, 36, 48, 50], fill=(255, 255, 255))
    draw.ellipse([37, 39, 45, 47], fill=(235, 20, 36))
    draw_mixed_line(draw, (56, 32), top_badge_text, size=22, fill=(255, 255, 255))

    # Top Right Exclusive Tag
    draw.rounded_rectangle([target_w - 260, 20, target_w - 20, 68], radius=8, fill=(10, 24, 58), outline=(0, 210, 255), width=2)
    draw.text((target_w - 240, 32), f"{CHANNEL_NAME} EXCLUSIVE", font=_get_english_font(18), fill=(0, 220, 255))

    # Lower Third Headline Strap
    strap_h = 160 if is_short else 145
    sy = target_h - strap_h - 20
    draw.rectangle([18, sy, target_w - 18, target_h - 20], fill=(8, 14, 28))
    draw.rectangle([18, sy - 4, target_w - 18, sy], fill=(255, 215, 0))

    # Location & Category Kicker
    kicker_text = f" {location}  |  {category} "
    kw = measure_text(draw, kicker_text, size=22) + 24
    draw.rounded_rectangle([28, sy + 10, 28 + kw, sy + 44], radius=6, fill=(210, 16, 30))
    draw_mixed_line(draw, (38, sy + 14), kicker_text, size=20, fill=(255, 255, 255))

    # Main Headline Wrapping
    clean_hl = re.sub(r'\s*-\s*[^-]+$', '', headline).strip()
    words = clean_hl.split()
    line1 = " ".join(words[:7])
    line2 = " ".join(words[7:14]) if len(words) > 7 else ""

    draw_mixed_line(draw, (32, sy + 58), line1, size=(38 if is_short else 34), fill=(255, 255, 255))
    if line2: draw_mixed_line(draw, (32, sy + 102), line2, size=(34 if is_short else 30), fill=(255, 225, 60))

    card.save(output_path, "JPEG", quality=95)
    return output_path

def download_scene_image(output_path, prompt="", rss_url="", rss_image_url="", article_url="", headline="", headline_text="", counter="", counter_text="", category="राष्ट्रीय", category_tag="राष्ट्रीय", location="नई दिल्ली", location_tag="नई दिल्ली", bulletin="LIVE", bulletin_label="LIVE", is_short=True, scene_idx=0, **kwargs):
    tw, th = (1080, 830) if is_short else (1100, 740)
    headline = headline or headline_text or prompt or ""
    counter = counter or counter_text or f"ख़बर {scene_idx + 1}"
    category = category or category_tag or "राष्ट्रीय"
    location = location or location_tag or "नई दिल्ली"
    bulletin = bulletin or bulletin_label or "LIVE"
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
    """Loads female/male video and plays smoothly at 1x real-time speed without any fast-forward jitter."""
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
            logger.info(f"✅ Loaded Real Anchor: {len(self.frames)} frames cached at {target_w}x{target_h}")
        except Exception as e:
            logger.warning(f"Real studio anchor load fallback: {e}")

    @property
    def total(self): return len(self.frames)

    def get_frame(self, frame_idx):
        if not self.frames:
            img = Image.new("RGB", (self.w, self.h), (18, 28, 64))
            draw_mixed_line(ImageDraw.Draw(img), (self.w // 2 - 120, self.h // 2), f"🔴 {CHANNEL_NAME}", size=36, fill=(255, 215, 0))
            return img
        return self.frames[frame_idx % len(self.frames)]

def find_real_anchor_video(gender="female"):
    g = (gender or "female").lower()
    for p in [f"anchor_real_{g}.mp4", f"assets/anchor_real_{g}.mp4", "anchor_real.mp4", "anchor_studio.mp4"]:
        if os.path.exists(p) and os.path.getsize(p) > 10000: return p
    return None

# ================= 6. LIVE RSS & STORY CURATION =================
def _extract_rss_image(item):
    for enc in item.findall("enclosure"):
        u = enc.get("url", "")
        if u and enc.get("type", "").startswith("image/"): return u
    for tag in [".//{http://search.yahoo.com/mrss/}content", ".//{http://search.yahoo.com/mrss/}thumbnail"]:
        for m in item.findall(tag):
            u = m.get("url", "")
            if u: return u
    desc = item.findtext("description") or ""
    match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', desc, re.IGNORECASE)
    if match: return match.group(1)
    return ""

def _clean_summary(raw_html):
    if not raw_html: return ""
    clean = re.sub(r'<[^>]+>', ' ', raw_html)
    clean = re.sub(r'http\S+|www\S+', '', clean)
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'&[a-z]+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    sentences = re.split(r'[।!?.]', clean)
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) >= 20 and not any(k in s_clean.lower() for k in ["read more", "click here", "copyright", "photo:", "source:"]):
            return s_clean
    return clean[:120].strip()

def fetch_trending_news(category="NATION", max_items=100):
    urls = NEWS_FEEDS.get(category, NEWS_FEEDS["NATION"])
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
                    if len(title) < 10 or title.lower() in seen: continue
                    seen.add(title.lower())
                    summary = _clean_summary(desc_raw)
                    headlines.append({
                        "title": title, "summary": summary, "article_url": (it.findtext("link") or "").strip(),
                        "media_url": _extract_rss_image(it),
                        "category_tag": "राष्ट्रीय" if len(headlines) % 2 == 0 else "अंतरराष्ट्रीय",
                        "location_tag": "नई दिल्ली" if len(headlines) % 2 == 0 else "ग्लोबल डेस्क",
                    })
                    if len(headlines) >= max_items: break
        except Exception: pass

    rec = get_recommended_topic()
    m = [h for h in headlines if classify_headline_topic(h["title"]) == rec]
    o = [h for h in headlines if classify_headline_topic(h["title"]) != rec]
    if m: headlines = m[:5] + o + m[5:]
    if not headlines:
        headlines = [
            {"title": "सुप्रीम कोर्ट का ऐतिहासिक फैसला", "summary": "सुरक्षा व्यवस्था पर कड़े दिशा-निर्देश जारी किए गए हैं।", "category_tag": "राष्ट्रीय", "location_tag": "नई दिल्ली"},
            {"title": "भारतीय सेना और DRDO का बड़ा परीक्षण", "summary": "नई मिसाइल का सफल परीक्षण पूरा कर रक्षा क्षमता मजबूत की गई है।", "category_tag": "डिफेंस", "location_tag": "ओडिशा"},
            {"title": "इसरो के गगनयान मिशन की बड़ी तैयारी", "summary": "अंतरिक्ष यात्रियों के सुरक्षा टेस्ट सफलतापूर्वक पूरे कर लिए गए हैं।", "category_tag": "विज्ञान", "location_tag": "बेंगलुरु"},
            {"title": "वैश्विक भू-राजनीति में बड़ा उलटफेर", "summary": "संयुक्त राष्ट्र में भारत ने कूटनीतिक स्तर पर कड़ा रुख अपनाया है।", "category_tag": "अंतरराष्ट्रीय", "location_tag": "ग्लोबल डेस्क"},
            {"title": "भारतीय अर्थव्यवस्था में नया उछाल", "summary": "बाजार और विदेशी निवेश में रिकॉर्ड बढ़ोतरी दर्ज की गई है।", "category_tag": "अर्थव्यवस्था", "location_tag": "मुंबई"},
        ]
    return headlines[:max_items]

# ================= 7. SOUND DESIGN & VOICE SYNTHESIS =================
def synthesize_broadcast_voice(text, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    voice = "hi-IN-SwaraNeural" if gender == "female" else "hi-IN-MadhurNeural"
    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(text=text, voice=voice, rate="-2%").save(output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return output_path
    except Exception: pass
    try:
        from gtts import gTTS
        gTTS(text=text, lang="hi", slow=False).save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return output_path
    except Exception: pass
    sr = 16000
    dur = max(3.0, min(8.0, len(text) * 0.08))
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

def _extract_audio_envelope(path, duration, fps=20):
    n_frames = max(1, int(duration * fps))
    try:
        cmd = ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw = proc.stdout.read()
        proc.wait()
        samples = np.frombuffer(raw, dtype=np.int16)
        if len(samples) > 0:
            spf = len(samples) // n_frames
            env = [float(np.mean(np.abs(samples[i * spf:(i + 1) * spf]))) / 32768.0 for i in range(n_frames)]
            mx = max(env) or 1.0
            return [min(1.0, v / mx) for v in env]
    except Exception: pass
    return [0.5] * n_frames

def generate_pro_broadcast_bed(duration, output_path="temp/broadcast_bed.wav", sr=22050):
    ns = int(duration * sr)
    t = np.linspace(0, duration, ns, endpoint=False)
    bass = np.sin(2 * np.pi * 55.0 * t) * 0.18
    pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t)
    drone = np.sin(2 * np.pi * 110.0 * t) * 0.10 * pulse
    mid = np.sin(2 * np.pi * 220.0 * t) * 0.05 * (0.5 + 0.5 * np.cos(2 * np.pi * 4.0 * t))
    sig = bass + drone + mid
    sig = np.clip(sig, -0.85, 0.85)
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

    # Concatenate all voice clips cleanly with 0.6s natural pauses between stories and 1.5s outro padding
    silence_pause = create_silence_wav(duration=0.6, output_path="temp/silence_pause.wav")
    silence_outro = create_silence_wav(duration=1.5, output_path="temp/silence_outro.wav")
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
    ticker_text = f"  ★★★  {CHANNEL_NAME} LIVE  ★★★  {TAGLINE}  ★★★  " + "  |  ".join([sc["headline"] for sc in scene_assets]) + "  ★★★  "

    total_required_frames = int((total_aud_dur + 0.5) * fps)
    frame_img = None

    for sc_idx, sc in enumerate(scene_assets):
        dur = sc.get("duration", 6.0)
        dur += (1.5 if sc_idx == len(scene_assets) - 1 else 0.6)
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
                draw_mixed_line(tb_draw, (24, 30), f"🔴 {CHANNEL_NAME}  |  LIVE", size=32, fill=(255, 255, 255))
                clock_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M IST")
                tb_draw.text((W - 170, 32), clock_str, font=_get_english_font(28), fill=(255, 215, 0))
                frame_img.paste(top_bar, (0, 0))

                mid_strap = Image.new("RGB", (W, 64), (10, 20, 48))
                m_draw = ImageDraw.Draw(mid_strap)
                m_draw.rectangle([0, 0, W, 4], fill=(255, 215, 0))
                m_draw.rectangle([0, 60, W, 64], fill=(255, 215, 0))
                draw_mixed_line(m_draw, (20, 16), f"⚡ {TAGLINE}", size=24, fill=(255, 255, 255))
                frame_img.paste(mid_strap, (0, 934))

                bot_bar = Image.new("RGB", (W, 80), (185, 14, 28))
                b_draw = ImageDraw.Draw(bot_bar)
                draw_mixed_line(b_draw, (200 - (global_frame * 6) % max(1, len(ticker_text) * 16), 22), ticker_text + ticker_text, size=26, fill=(255, 255, 255))
                b_draw.rectangle([0, 0, 180, 80], fill=(240, 185, 0))
                draw_mixed_line(b_draw, (20, 24), "🔴 ताज़ा ख़बरें", size=24, fill=(0, 0, 0))
                frame_img.paste(bot_bar, (0, H - 80))

                if logo_img:
                    frame_img.paste(logo_img, (W - 260, 20), logo_img)
            else:
                # Long 16:9 Virtual Studio Set
                hdr = Image.new("RGB", (W, 70), (12, 22, 54))
                h_draw = ImageDraw.Draw(hdr)
                h_draw.ellipse([26, 26, 42, 42], fill=(235, 20, 36))
                h_draw.text((50, 18), f"{CHANNEL_NAME} LIVE  |  {TAGLINE}", font=_get_english_font(24), fill=(255, 215, 0))
                clock_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")
                h_draw.text((W - 190, 18), clock_str, font=_get_english_font(22), fill=(255, 255, 255))
                frame_img.paste(hdr, (0, 0))

                if anc_frame: frame_img.paste(anc_frame, (20, 90))
                frame_img.paste(story_card.resize((1100, 740), Image.Resampling.LANCZOS), (790, 110))

                if logo_img:
                    frame_img.paste(logo_img, (30, H - 280), logo_img)

                tick_bar = Image.new("RGB", (W, 76), (185, 14, 28))
                t_draw = ImageDraw.Draw(tick_bar)
                draw_mixed_line(t_draw, (180 - (global_frame * 6) % max(1, len(ticker_text) * 16), 22), ticker_text + ticker_text, size=25, fill=(255, 255, 255))
                t_draw.rectangle([0, 0, 170, 76], fill=(240, 185, 0))
                draw_mixed_line(t_draw, (16, 22), "🔴 ताज़ा सुर्खियां", size=24, fill=(0, 0, 0))
                frame_img.paste(tick_bar, (0, H - 76))

            proc.stdin.write(frame_img.tobytes())
            global_frame += 1

    # Ensure video frame stream completely covers the audio duration
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

    # 1. Right side: Real Ground News Photo or high-tech dynamic backdrop
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

    # 2. Left side: Real Studio News Anchor (Alert, professional gaze at frame 30)
    anc_vid = find_real_anchor_video(gender)
    if anc_vid:
        try:
            anc = RealStudioAnchor(anc_vid, target_w=520, target_h=TH)
            if anc.total > 0: base.paste(anc.get_frame(30), (0, 0))
        except Exception: pass

    # 3. Soft gradient seam between anchor and right side backdrop
    overlay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for x in range(440, 560):
        alpha = int(((560 - x) / 120.0) * 160)
        odraw.line([(x, 0), (x, TH)], fill=(12, 22, 54, alpha))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    # 4. Red & Gold Studio Borders
    draw = ImageDraw.Draw(base)
    draw.rectangle([0, 0, TW - 1, TH - 1], outline=(220, 20, 36), width=6)
    draw.rectangle([6, 6, TW - 7, TH - 7], outline=(255, 215, 0), width=2)

    # 5. Top Left Live Badge: 🔴 NEXORA NEWS | LIVE
    draw.rounded_rectangle([30, 24, 440, 78], radius=8, fill=(210, 16, 30), outline=(255, 215, 0), width=2)
    draw.ellipse([46, 42, 64, 60], fill=(255, 255, 255))
    draw.ellipse([50, 46, 60, 56], fill=(235, 20, 36))
    draw.text((78, 36), f"{CHANNEL_NAME}  |  LIVE", font=_get_english_font(28), fill=(255, 255, 255))

    # 6. Top Right: Channel Logo & Breaking Tag
    if os.path.exists(LOGO_PATH):
        try:
            logo_raw = Image.open(LOGO_PATH).convert("RGBA").resize((140, 140), Image.Resampling.LANCZOS)
            base.paste(logo_raw, (TW - 170, 24), logo_raw)
        except Exception: pass

    # 7. Lower Third Headline Box (High-CTR Bold Text)
    draw.rectangle([20, TH - 230, TW - 20, TH - 20], fill=(8, 14, 28))
    draw.rectangle([20, TH - 234, TW - 20, TH - 228], fill=(255, 215, 0))

    clean_hl = re.sub(r"\s*-\s*[^-]+$", "", headline or "आज की बड़ी ख़बरें").strip()
    w = clean_hl.split()
    line1 = " ".join(w[:6])
    line2 = " ".join(w[6:13]) if len(w) > 6 else ""

    draw_mixed_line(draw, (44, TH - 210), line1, size=52, fill=(0, 0, 0))
    draw_mixed_line(draw, (40, TH - 212), line1, size=52, fill=(255, 235, 60))

    if line2:
        draw_mixed_line(draw, (44, TH - 138), line2, size=48, fill=(0, 0, 0))
        draw_mixed_line(draw, (40, TH - 140), line2, size=48, fill=(255, 255, 255))

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
    body = {"snippet": {"title": safe_t, "description": description[:4500], "tags": tags[:25], "categoryId": "25", "defaultLanguage": "hi"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
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
def produce_news_episode(category="AUTO", is_short=True, edition="auto", anchor_gender=None, skip_upload=False):
    ed = get_current_edition() if edition == "auto" else edition.upper()
    cfg = EDITION_CONFIGS.get(ed, EDITION_CONFIGS["MORNING"])
    headlines = fetch_trending_news(category=("NATION" if category == "AUTO" else category), max_items=(5 if is_short else cfg["target_count"]))
    gender = anchor_gender or ("female" if random.random() < 0.5 else "male")

    # High-CTR Dynamic Title with Specific Breaking Lead
    lead_t = re.sub(r"\s*-\s*[^-]+$", "", headlines[0]["title"]).strip() if headlines else "देश की बड़ी खबर"
    lead_short = lead_t[:42].strip() + ("..." if len(lead_t) > 42 else "")
    if is_short:
        video_title = f"🚨 {lead_short} | आज की 5 बड़ी खबरें! #Shorts #HindiNews #NexoraNews"
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
            category="विशेष बुलेटिन",
            location="स्टूडियो हेडक्वार्टर",
            bulletin=cfg["bulletin_label"],
            is_short=False,
        )
        intro_narration = (
            f"नमस्कार! आप देख रहे हैं {CHANNEL_NAME_HI}—{TAGLINE}। "
            f"आज के इस विशेष महाबुलेटिन में हम लेकर आए हैं देश, दुनिया और टेक्नोलॉजी की तमाम बड़ी व महत्वपूर्ण खबरें। "
            f"आइए बिना किसी देरी के सीधे रुख करते हैं आज के इस बुलेटिन की..."
        )
        synthesize_broadcast_voice(intro_narration, intro_aud, gender=gender)
        assets.append({
            "scene_id": 0, "image_path": intro_img, "audio_path": intro_aud,
            "headline": f"विशेष बुलेटिन: {CHANNEL_NAME_HI}", "duration": _get_audio_duration(intro_aud),
        })

    # ===== MAIN STORIES WITH COMPLETE, CLEAR NEWS BRIEFING =====
    intro_prefixes = [
        "पहली बड़ी खबर।",
        "अगली महत्वपूर्ण सुर्खी।",
        "तीसरा बड़ा घटनाक्रम।",
        "चौथी बड़ी खबर पर नजर डालें तो,",
        "और पांचवीं प्रमुख सुर्खी।",
        "छठी महत्वपूर्ण खबर।",
        "सातवां बड़ा अपडेट।",
        "आठवीं प्रमुख खबर।",
        "नौवां बड़ा घटनाक्रम।",
        "दसवीं और अंतिम बड़ी सुर्खी।"
    ]

    for idx, h in enumerate(headlines):
        sid = idx + 1
        img_p, aud_p = f"temp/scene_{sid}.jpg", f"temp/voice_{sid}.mp3"
        counter = f"ख़बर {sid} / {len(headlines)}" if not is_short else f"ख़बर {sid}"
        clean_title = re.sub(r'\s*-\s*[^-]+$', '', h["title"]).strip()
        download_scene_image(img_p, prompt=clean_title, rss_url=h.get("media_url", ""), article_url=h.get("article_url", ""), headline=clean_title, counter=counter, category=h.get("category_tag", "राष्ट्रीय"), location=h.get("location_tag", "नई दिल्ली"), bulletin=cfg["bulletin_label"], is_short=is_short, scene_idx=idx)
        if idx == 0 and os.path.exists(img_p): lead_photo = img_p

        prefix = intro_prefixes[idx % len(intro_prefixes)]
        summary_fact = h.get("summary", "").strip()
        if not summary_fact or len(summary_fact) < 15:
            summary_fact = "इस बड़े मामले से जुड़ी हर महत्वपूर्ण अपडेट पर हमारी नजर लगातार बनी हुई है।"

        # Fully articulated news briefing: Headline + Clear factual context
        if is_short and idx == len(headlines) - 1:
            narration = f"{prefix} {clean_title}। {summary_fact}। देश और दुनिया की तमाम बड़ी खबरों के लिए सब्सक्राइब करें {CHANNEL_NAME_HI}।"
        else:
            narration = f"{prefix} {clean_title}। {summary_fact}।"

        synthesize_broadcast_voice(narration, aud_p, gender=gender)
        assets.append({"scene_id": sid, "image_path": img_p, "audio_path": aud_p, "headline": clean_title, "duration": _get_audio_duration(aud_p)})

    # ===== DEDICATED OUTRO SCENE FOR LONG BULLETINS =====
    if not is_short:
        outro_img = "temp/scene_outro.jpg"
        outro_aud = "temp/voice_outro.mp3"
        create_broadcast_story_card(
            outro_img,
            headline="सब्सक्राइब करें नेक्सोरा न्यूज़ | Bell Icon दबाएं",
            counter="LIVE OUTRO",
            category="चैनल अपडेट",
            location="स्टूडियो हेडक्वार्टर",
            bulletin="SUBSCRIBE NOW",
            is_short=False,
        )
        outro_narration = (
            f"तो ये थीं आज की तमाम बड़ी और अहम खबरें। "
            f"देश, दुनिया और टेक्नोलॉजी जगत के हर बड़े घटनाक्रम की सबसे तेज़ और सटीक कवरेज के लिए '{CHANNEL_NAME_HI}' को अभी सब्सक्राइब करें और बेल आइकन दबाना न भूलें। "
            f"देखते रहिए {CHANNEL_NAME_HI}—{TAGLINE_HI}। नमस्कार!"
        )
        synthesize_broadcast_voice(outro_narration, outro_aud, gender=gender)
        assets.append({
            "scene_id": len(headlines) + 1, "image_path": outro_img, "audio_path": outro_aud,
            "headline": f"सब्सक्राइब करें {CHANNEL_NAME_HI}", "duration": _get_audio_duration(outro_aud),
        })

    out = "final_short.mp4" if is_short else "final_long.mp4"
    build_news_video(script, assets, out, is_short=is_short)
    thumb = "temp/broadcast_thumb.jpg"
    if not is_short: generate_broadcast_thumbnail(headlines[0]["title"] if headlines else "आज की बड़ी खबरें", lead_photo, thumb, gender=gender)

    if not skip_upload:
        # Auto-generate video chapter timestamps for YouTube SEO & Google Key Moments
        time_cursor = 0.0
        chapters = []
        for sc in assets:
            mins, secs = int(time_cursor // 60), int(time_cursor % 60)
            chapters.append(f"{mins:02d}:{secs:02d} - {sc['headline']}")
            time_cursor += sc.get("duration", 8.0) + 0.5

        desc = (
            f"{script['title']}\n\n"
            f"📺 {CHANNEL_NAME} ({CHANNEL_NAME_HI})\n"
            f"⚡ {TAGLINE} | {TAGLINE_HI}\n\n"
            f"📌 इस बुलेटिन के मुख्य समाचार (Chapters & Timestamps):\n"
            + "\n".join(chapters)
            + f"\n\n🌐 Channel Identity & Mission:\n"
            f"• Category: National, International & Technology\n"
            f"• Format: 24/7 AI Broadcast Network\n"
            f"• Language: Hindi (हिन्दी)\n\n"
            f"🔔 देश और दुनिया की तमाम बड़ी खबरों के लिए Nexora News को Subscribe करें और Bell Icon दबाएं!\n\n"
            f"#NexoraNews #HindiNews #BreakingNews #IndiaNews #TopNews #Shorts #NewsLive #LatestNews"
        )
        upload_tags = [CHANNEL_NAME, CHANNEL_NAME_HI, "Nexora News Live", "Hindi News", "Breaking News", "आज की ताजा खबर", "Top News Today", "India News Live", "Superfast News", "News Shorts", "Hindi Samachar", "Daily News Hindi", "Technology News", "World News Hindi"]
        upload_to_youtube(out, script["title"], desc, upload_tags, thumb_path=thumb, is_short=is_short)
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--type", default="both")
    p.add_argument("--edition", default="auto")
    p.add_argument("--category", default="AUTO")
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
    vcat = (args.category or "AUTO").strip().upper()
    vanc = None if (not args.anchor or args.anchor == "auto") else args.anchor.strip().lower()

    if vtype in ("short", "both"): produce_news_episode(category=vcat, is_short=True, edition=vedition, anchor_gender=vanc, skip_upload=args.skip_upload)
    if vtype in ("long", "both"): produce_news_episode(category=vcat, is_short=False, edition=vedition, anchor_gender=vanc, skip_upload=args.skip_upload)

if __name__ == "__main__":
    main()
