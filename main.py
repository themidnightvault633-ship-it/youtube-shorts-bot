#!/usr/bin/env python3
"""
NEXORA NEWS - v6.0 Complete Autonomous Television Network & Monetization Master Engine
Zero-to-Monetized Architecture:
1. 4-Format Duration Matrix:
   - VIRAL SHORT (35-48s, 9:16): 1 Lead Story + Fast Hook + Debate Question (Subscriber Engine)
   - BREAKING FLASH (2-3m, 16:9): 1 Mega Story Deep-Dive (3 Visual Chapters) when Viral Score >= 85
   - STANDARD BULLETIN (5-6m, 16:9): 6 Global Stories x ~50s In-Depth Analysis (Watch-Time Engine)
   - PRIME-TIME DOCUMENTARY SPECIAL (8-10m, 16:9): 8-10 Stories + Extended Geopolitical Analysis (8m+ Mid-Roll Ads Revenue)
2. Global Prime-Time Schedule Router (US/UK/Europe/India Peak Traffic Windows)
3. Dual-Anchor Co-Hosting: Male & Female anchors alternate stories within Long Broadcasts (100% YPP Original Value)
4. 3-Layer Visual Story Progression: Each story transitions across 3 distinct visual cards (Headline -> KEY FACTS -> GLOBAL IMPACT)
5. Persistent GitHub Ledger (assets/broadcast_history.json): 100% immune to YouTube 403 scope issues; zero duplicate stories
6. Auto-Playlist Organizer, Auto-Chapters (00:00), and Auto-Pinned Debate Question Comment
"""
import os, sys, re, glob, json, time, math, html, random, asyncio, logging, argparse, subprocess, urllib.parse, wave
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("NexoraMasterV6")

# ================= 1. BRANDING & CREDENTIALS =================
def _clean(v): return (v or "").strip().strip('"').strip("'").strip()
GEMINI_API_KEY = _clean(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean(os.environ.get("YT_REFRESH_TOKEN", ""))

CHANNEL_NAME = "NEXORA NEWS"
TAGLINE = "THE WORLD. THE NEXT. THE NEWS."
SUB_TAGLINE = "GLOBAL COVERAGE | INDEPENDENT | VERIFIED"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
STUDIO_BG_PATH = os.path.join("assets", "studio_background.jpg")
HISTORY_FILE = os.path.join("assets", "broadcast_history.json")

NORMAL_COOLDOWN_HOURS = 2.8     # Safe gap (~6-8 uploads/day) within YouTube API daily quota
BREAKING_COOLDOWN_HOURS = 1.0   # Immediate override when Mega Breaking News (score >= 85) hits

GLOBAL_TOPICS = {
    "DEFENSE & SECURITY": ["military", "pentagon", "defense", "missile", "navy", "warship", "fighter jet", "aircraft carrier", "army", "conflict", "troops", "soldiers", "ukraine", "nato", "nuclear", "drone", "strike", "war"],
    "US & GEOPOLITICS": ["trump", "biden", "white house", "washington", "congress", "senate", "putin", "kremlin", "xi jinping", "china", "taiwan", "israel", "gaza", "iran", "united nations", "sanctions", "diplomacy", "summit", "apec"],
    "GLOBAL ECONOMY": ["federal reserve", "interest rate", "inflation", "oil", "gold", "tariffs", "wall street", "stock market", "imf", "dollar", "gdp", "recession", "billion", "trillion", "bank", "trade war"],
    "AI & FUTURE TECH": ["artificial intelligence", "openai", "nvidia", "elon musk", "spacex", "nasa", "tesla", "apple", "google", "microsoft", "semiconductor", "chip", "quantum", "cyber", "hack", "outage", "robot"],
    "GLOBAL CRISIS": ["crash", "earthquake", "hurricane", "wildfire", "tsunami", "emergency", "explosion", "dead", "killed", "rescue", "alert", "warning"]
}

VIRAL_WEIGHTS = {
    "breaking": 35, "war": 35, "strike": 35, "missile": 35, "nuclear": 35, "invasion": 35,
    "explosion": 35, "crash": 30, "assassination": 35, "emergency": 30, "collapse": 30,
    "trump": 28, "putin": 28, "elon musk": 28, "xi jinping": 25, "netanyahu": 25, "zelensky": 25,
    "white house": 24, "pentagon": 25, "nato": 25, "kremlin": 25, "taiwan": 25, "iran": 25, "israel": 24,
    "nvidia": 24, "openai": 24, "chatgpt": 24, "spacex": 24, "nasa": 22, "bitcoin": 22,
    "federal reserve": 24, "tariffs": 24, "sanctions": 24, "billion": 20, "trillion": 25,
    "cyberattack": 24, "hacked": 22, "outage": 22
}

STOPWORDS = {
    "about", "after", "against", "alert", "almost", "another", "around", "before", "being", "between",
    "breaking", "could", "deeply", "during", "first", "found", "global", "hours", "international",
    "lasting", "latest", "major", "nexora", "other", "people", "report", "reports", "should", "since",
    "sorry", "still", "their", "there", "these", "thing", "think", "those", "through", "today",
    "under", "until", "update", "updates", "what", "where", "which", "while", "world", "would", "shorts",
    "plan", "plans", "historic", "joint", "meeting", "next", "week", "says", "expect", "news", "video",
    "with", "from", "that", "this", "have", "will", "into", "over", "more", "than", "were", "been"
}

def _clean_text(raw):
    if not raw: return ""
    t = html.unescape(str(raw))
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def classify_headline_topic(headline):
    hl = headline.lower()
    for topic, kws in GLOBAL_TOPICS.items():
        if any(k in hl for k in kws): return topic
    return "WORLD AFFAIRS"

def score_story_virality(title, summary):
    text = f"{title} {summary}".lower()
    score = 20
    for kw, pts in VIRAL_WEIGHTS.items():
        if kw in text:
            score += pts
    if re.search(r"\b\d+\b", title):
        score += 12
    if any(w in text for w in ["recipe", "fashion", "horoscope", "footballer", "striker", "cricket", "celebrity", "tennis", "golf"]):
        score -= 35
    return score

ENTITY_MAP_INTL = [
    (["microsoft", "outage", "azure", "windows", "teams"], "Microsoft corporate headquarters technology server cloud outage news"),
    (["nvidia", "chip", "semiconductor", "ai", "openai"], "modern artificial intelligence server data center microchip technology"),
    (["binance", "crypto", "hack", "bitcoin", "blockchain"], "digital cryptocurrency blockchain server data center security tech"),
    (["jet", "crash", "aviation", "airplane", "flight", "airline"], "international commercial airport airplane runway terminal aviation transport"),
    (["gaza", "israel", "strike", "middle east", "lebanon", "iran"], "Middle East diplomacy security emergency press conference"),
    (["white house", "president", "biden", "trump", "washington", "congress"], "White House Washington DC Capitol press briefing President United States"),
    (["united nations", "un security council", "diplomacy", "summit", "apec"], "United Nations Security Council chamber Geneva New York diplomacy"),
    (["nato", "pentagon", "defense", "allies"], "NATO headquarters summit Brussels defense ministers alliance meeting"),
    (["aircraft carrier", "navy", "warship", "fighter jet", "troops", "ukraine", "missile"], "military defense tactical operation warship fighter jet"),
    (["space", "nasa", "spacex", "rocket", "satellite", "musk"], "NASA SpaceX rocket launch pad space exploration satellite deployment"),
    (["kremlin", "russia", "putin", "moscow"], "Kremlin Red Square Moscow official government architecture"),
    (["china", "beijing", "xi jinping", "taiwan"], "Beijing China Great Hall international diplomacy summit"),
    (["wall street", "stock", "market", "fed", "inflation", "tariff", "economy"], "Wall Street New York Stock Exchange financial district global markets")
]

def map_headline_to_search_query(headline):
    hl = headline.lower()
    for kw_list, query in ENTITY_MAP_INTL:
        if any(k in hl for k in kw_list): return query
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", headline)
    words = [w for w in clean.split() if len(w) > 3 and w.lower() not in STOPWORDS]
    return " ".join(words[:5]) + " press photo news"

# ================= 2. 24-HOUR GLOBAL BROADCAST SCHEDULE MATRIX =================
def select_optimal_broadcast_mode(utc_hour, last_format, lead_viral_score, requested_type="auto"):
    """
    Decides exact video format, target duration, and story count based on Global Prime-Time Windows:
    - If Mega Breaking News (score >= 85) & last was short -> BREAKING_FLASH (2-3 min urgent report) or SHORT
    - 17:00 - 22:00 UTC (US Morning/Noon + Europe Evening Peak) -> PRIME_DOCUMENTARY (8-10 min, 8 stories for Mid-Roll Ads!)
    - 05:00 - 10:00 UTC (Europe Morning + India/Asia Daytime) -> STANDARD_BULLETIN (5-6 min, 6 stories)
    - Alternates with VIRAL_SHORT (40-50 sec, 1 story) so Subscribers & Watch-Time grow together.
    """
    if requested_type == "short":
        return "VIRAL_SHORT", True, 1, "BREAKING NEWS SHORT"
    if requested_type == "long":
        if 17 <= utc_hour <= 22:
            return "PRIME_DOCUMENTARY", False, 8, "PRIME TIME SPECIAL REPORT (8-10 MIN)"
        return "STANDARD_BULLETIN", False, 6, "GLOBAL NEWS BULLETIN (5 MIN)"

    # Auto mode: alternate between Short and Long formats
    if last_format != "short":
        return "VIRAL_SHORT", True, 1, "VIRAL BREAKING SHORT"

    # Next is a 16:9 Long Video: choose between 3m Breaking Flash, 5m Bulletin, or 9m Prime Documentary
    if lead_viral_score >= 90 and utc_hour not in (6, 7, 13, 14, 18, 19, 20):
        return "BREAKING_FLASH", False, 3, "URGENT BREAKING NEWS FLASH"
    elif 17 <= utc_hour <= 22 or 12 <= utc_hour <= 14:
        return "PRIME_DOCUMENTARY", False, 8, "PRIME TIME IN-DEPTH SPECIAL"
    else:
        return "STANDARD_BULLETIN", False, 6, "GLOBAL HEADLINES BULLETIN"

# ================= 3. TYPOGRAPHY & TEXT ENGINE =================
def _get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def wrap_text_to_width(text, font, max_width, max_lines=4):
    words = (text or "").split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        try: w_px = font.getbbox(test)[2] - font.getbbox(test)[0]
        except Exception: w_px = len(test) * (font.size * 0.55 if hasattr(font, 'size') else 10)
        if w_px <= max_width: cur.append(w)
        else:
            if cur: lines.append(" ".join(cur))
            cur = [w]
            if len(lines) >= max_lines: break
    if cur and len(lines) < max_lines: lines.append(" ".join(cur))
    return lines

# ================= 4. MULTI-CARD VISUAL ENGINE (KEN BURNS + INFOGRAPHICS) =================
def upgrade_image_url(u):
    if not u: return ""
    u = re.sub(r'/news/\d+/', '/news/1024/', u)
    u = re.sub(r'/ace/standard/\d+/', '/ace/standard/1024/', u)
    u = re.sub(r'/images/ic/\d+xn/', '/images/ic/1024xn/', u)
    u = re.sub(r'/\d+x\d+/', '/1024x576/', u)
    return u

def _validate_image(data):
    if not data or len(data) < 2500: raise ValueError("Data too small")
    img = Image.open(BytesIO(data)).convert("RGB")
    w, h = img.size
    if w < 120 or h < 120: raise ValueError(f"Dim too small {w}x{h}")
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.10)
    img = ImageEnhance.Sharpness(img).enhance(1.28)
    return img

def _fetch_article_og_image(url):
    if not url: return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', resp.text, re.IGNORECASE)
            if not m: m = re.search(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', resp.text, re.IGNORECASE)
            if m:
                img_url = upgrade_image_url(m.group(1).replace("&amp;", "&"))
                r2 = requests.get(img_url, headers=HEADERS, timeout=6)
                if r2.status_code == 200: return _validate_image(r2.content)
    except Exception: pass
    return None

def _fetch_ground_news_photo(query):
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"file:{query}", "gsrlimit": 5, "prop": "imageinfo", "iiprop": "url|size|mime"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                for ii in pdata.get("imageinfo", []):
                    u = ii.get("url", "")
                    if u.lower().endswith((".jpg", ".jpeg", ".png")) and ii.get("width", 0) >= 400:
                        r2 = requests.get(u, headers=HEADERS, timeout=6)
                        if r2.status_code == 200: return _validate_image(r2.content)
    except Exception: pass
    return None

def _fetch_pollinations_image(prompt, w=1280, h=720):
    try:
        safe_prompt = urllib.parse.quote(f"editorial press photography, Reuters photojournalism, authentic news scene: {prompt}, high detail, 8k")
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={w}&height={h}&nologo=true&model=turbo"
        r = requests.get(url, timeout=8)
        if r.status_code == 200: return _validate_image(r.content)
    except Exception: pass
    return None

def download_raw_scene_photo(scene_info, output_path, target_w=1160, target_h=928):
    img = None
    if scene_info.get("article_url"):
        img = _fetch_article_og_image(scene_info["article_url"])

    if not img or (img and img.size[0] < 500):
        u = scene_info.get("image_url", "")
        if u and u.startswith("http"):
            u = upgrade_image_url(u)
            try:
                r = requests.get(u, headers=HEADERS, timeout=6)
                if r.status_code == 200:
                    cand = _validate_image(r.content)
                    if not img or cand.size[0] > img.size[0]: img = cand
            except Exception: pass

    if not img or (img and img.size[0] < 400):
        q = map_headline_to_search_query(scene_info["headline"])
        cand = _fetch_ground_news_photo(q)
        if cand: img = cand

    if not img or (img and img.size[0] < 400):
        cand = _fetch_pollinations_image(scene_info["headline"], w=target_w, h=target_h)
        if cand: img = cand

    if not img and os.path.exists(STUDIO_BG_PATH):
        try: img = Image.open(STUDIO_BG_PATH).convert("RGB")
        except Exception: pass

    if not img:
        img = Image.new("RGB", (target_w, target_h), (14, 24, 52))

    over_w, over_h = int(target_w * 1.18), int(target_h * 1.18)
    bw, bh = img.size
    scale = max(over_w / bw, over_h / bh)
    nw, nh = int(bw * scale), int(bh * scale)
    res = img.resize((nw, nh), Image.Resampling.LANCZOS)
    cx, cy = (nw - over_w) // 2, (nh - over_h) // 2
    cropped = res.crop((cx, cy, cx + over_w, cy + over_h))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cropped.save(output_path, quality=95)
    return output_path

def render_animated_story_card(raw_img, sc_data, target_w, target_h, progress_ratio=0.0, caption_chunk="", is_short=False):
    """
    3-Phase Visual Progression during each story so visuals change every 12-15 seconds:
    - Phase 1 (0% - 38%): Full-Bleed Spot Photo + Ken Burns Zoom + Lower-Third Headline
    - Phase 2 (38% - 72%): 'KEY DEVELOPMENTS' Broadcast Infographic Overlay Card (on Long videos)
    - Phase 3 (72% - 100%): 'STRATEGIC GLOBAL IMPACT' Editorial Analysis Card (100% YPP Original Value)
    """
    headline = sc_data["headline"]
    category = sc_data.get("category", "WORLD")
    key_fact = sc_data.get("key_fact", "")
    why_matters = sc_data.get("why_it_matters", "")

    bw, bh = raw_img.size
    zoom = 1.0 + (0.14 * min(1.0, max(0.0, progress_ratio)))
    crop_w = int(target_w / zoom)
    crop_h = int(target_h / zoom)
    cx = (bw - crop_w) // 2
    cy = (bh - crop_h) // 2
    card = raw_img.crop((cx, cy, cx + crop_w, cy + crop_h)).resize((target_w, target_h), Image.Resampling.BILINEAR)

    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(int(target_h * 0.40), target_h):
        alpha = int(242 * ((y - int(target_h * 0.40)) / (target_h * 0.60)))
        odraw.line([(0, y), (target_w, y)], fill=(6, 10, 26, alpha))
    card.paste(overlay, (0, 0), overlay)

    draw = ImageDraw.Draw(card)
    clean_cat = category.replace("_", " ").upper()
    badge_w, badge_h = max(240, len(clean_cat) * 14 + 44), 44
    draw.rectangle([32, 30, 32 + badge_w, 30 + badge_h], fill=(185, 14, 28))
    draw.rectangle([32 + badge_w, 30, 32 + badge_w + 6, 30 + badge_h], fill=(255, 215, 0))
    draw.text((46, 40), f"● {clean_cat}", font=_get_font(22, bold=True), fill=(255, 255, 255))

    # Top-Right Phase Badge
    phase_label = "LIVE COVERAGE"
    if not is_short and 0.38 <= progress_ratio < 0.72 and key_fact:
        phase_label = "KEY INTELLIGENCE"
    elif not is_short and progress_ratio >= 0.72 and why_matters:
        phase_label = "GLOBAL IMPACT"

    src_w = 235
    draw.rectangle([target_w - src_w - 32, 30, target_w - 32, 72], fill=(10, 18, 42))
    draw.rectangle([target_w - src_w - 32, 30, target_w - 32, 72], outline=(255, 215, 0), width=2)
    draw.text((target_w - src_w - 14, 41), f"★ {phase_label}", font=_get_font(18, bold=True), fill=(255, 215, 0))

    # Phase 2 & 3 Mid-Screen Editorial Graphic Card on Long Videos (Boosts Retention & YPP Originality)
    if not is_short and progress_ratio >= 0.38 and (key_fact or why_matters):
        info_title = "KEY INTELLIGENCE BRIEFING" if progress_ratio < 0.72 else "WHY THIS MATTERS GLOBALLY"
        info_body = key_fact if (progress_ratio < 0.72 and key_fact) else (why_matters or key_fact)
        if info_body:
            info_font = _get_font(28, bold=True)
            info_lines = wrap_text_to_width(info_body, info_font, target_w - 140, max_lines=3)
            icard_h = len(info_lines) * 40 + 88
            icard_y = 115
            icard = Image.new("RGBA", (target_w - 64, icard_h), (8, 16, 40, 222))
            idraw = ImageDraw.Draw(icard)
            idraw.rectangle([0, 0, target_w - 64, icard_h], outline=(255, 215, 0), width=2)
            idraw.rectangle([0, 0, 10, icard_h], fill=(185, 14, 28, 255))
            idraw.text((28, 16), f"■ {info_title}", font=_get_font(22, bold=True), fill=(255, 215, 0))
            iy = 58
            for iline in info_lines:
                idraw.text((28, iy), iline, font=info_font, fill=(255, 255, 255))
                iy += 40
            card.paste(icard, (32, icard_y), icard)

    # Bottom Lower-Third Headline Plate
    f_size = 36 if target_w >= 1000 else 28
    font_hl = _get_font(f_size, bold=True)
    wrapped = wrap_text_to_width(headline, font_hl, target_w - 100, max_lines=3)
    box_h = (len(wrapped) * (f_size + 10)) + 32
    box_y = target_h - box_h - 22

    glass_plate = Image.new("RGBA", (target_w - 48, box_h), (8, 14, 32, 230))
    gdraw = ImageDraw.Draw(glass_plate)
    gdraw.rectangle([0, 0, 8, box_h], fill=(255, 215, 0, 255))
    card.paste(glass_plate, (24, box_y), glass_plate)

    draw = ImageDraw.Draw(card)
    y_text = box_y + 16
    for line in wrapped:
        draw.text((50, y_text + 2), line, font=font_hl, fill=(0, 0, 0))
        draw.text((48, y_text), line, font=font_hl, fill=(255, 255, 255))
        y_text += f_size + 10

    # Synchronized Live Teleprompter Subtitle Pill
    if caption_chunk:
        cap_font = _get_font(25, bold=True)
        cap_lines = wrap_text_to_width(caption_chunk.upper(), cap_font, target_w - 140, max_lines=1)
        if cap_lines:
            cline = cap_lines[0]
            pill_y = box_y - 54
            pill = Image.new("RGBA", (target_w - 96, 44), (185, 14, 28, 238))
            pdraw = ImageDraw.Draw(pill)
            pdraw.rectangle([0, 0, 6, 44], fill=(255, 215, 0, 255))
            card.paste(pill, (48, pill_y), pill)
            draw = ImageDraw.Draw(card)
            draw.text((68, pill_y + 9), f"🎙️ {cline}", font=cap_font, fill=(255, 255, 255))

    return card

def create_broadcast_outro_card(output_path="temp/card_outro.jpg", target_w=1160, target_h=928, studio_bg_path="assets/studio_background.jpg", is_short=False):
    over_w, over_h = int(target_w * 1.16), int(target_h * 1.16)
    card = Image.new("RGB", (over_w, over_h), (10, 16, 36))
    if os.path.exists(studio_bg_path):
        try:
            bg = Image.open(studio_bg_path).convert("RGB")
            bw, bh = bg.size
            scale = max(over_w / bw, over_h / bh)
            nw, nh = int(bw * scale), int(bh * scale)
            res = bg.resize((nw, nh), Image.Resampling.LANCZOS)
            cx, cy = (nw - over_w) // 2, (nh - over_h) // 2
            card.paste(res.crop((cx, cy, cx + over_w, cy + over_h)), (0, 0))
        except Exception: pass
        
    overlay = Image.new("RGBA", (over_w, over_h), (8, 14, 32, 220))
    card.paste(overlay, (0, 0), overlay)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    card.save(output_path, quality=95)
    return output_path

# ================= 5. DUAL-ANCHOR STUDIO VIDEO ENGINE =================
class RealStudioAnchor:
    def __init__(self, video_path, target_w, target_h):
        self.target_w, self.target_h = target_w, target_h
        self.frames = []
        if video_path and os.path.exists(video_path):
            try:
                vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
                cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", vf, "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                frame_bytes = target_w * target_h * 3
                while True:
                    raw = p.stdout.read(frame_bytes)
                    if not raw or len(raw) < frame_bytes: break
                    self.frames.append(Image.frombytes("RGB", (target_w, target_h), raw))
                p.wait()
            except Exception as e:
                logger.warning(f"Failed to load anchor video: {e}")
                
        is_male_vid = "male" in str(video_path).lower() or "1000124448" in str(video_path)
        if is_male_vid and len(self.frames) >= 65:
            fwd = self.frames[15:65]
            self.active_loop = fwd + fwd[::-1]
            self.resting_frame = self.frames[0]
        elif len(self.frames) >= 140:
            fwd = self.frames[85:140]
            self.active_loop = fwd + fwd[::-1]
            self.resting_frame = self.frames[140]
        elif len(self.frames) >= 50:
            fwd = self.frames[15:50]
            self.active_loop = fwd + fwd[::-1]
            self.resting_frame = self.frames[0]
        else:
            blank = Image.new("RGB", (target_w, target_h), (12, 18, 36))
            self.active_loop = [blank]
            self.resting_frame = blank

    def get_frame(self, idx, is_speaking=True):
        if not is_speaking:
            return self.resting_frame
        return self.active_loop[idx % len(self.active_loop)]

def find_real_anchor_video(gender="female"):
    if gender.lower() == "male":
        candidates = [
            "anchor_real_male.mp4", "anchor_real_male.mp4.mp4", "anchor_real_male..mp4", "1000124448.mp4", "male_anchor.mp4", "anchor_male.mp4",
            os.path.join("assets", "anchor_real_male.mp4")
        ]
    else:
        candidates = [
            "anchor_real_female.mp4", "anchor_real_female.mp4.mp4", "anchor_real_female..mp4", "1000124449.mp4", "female_anchor.mp4", "anchor_female.mp4",
            "anchor_real.mp4", os.path.join("assets", "anchor_real_female.mp4")
        ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 2000000:
            return c
    for c in candidates:
        if os.path.exists(c) and "pixverse" not in c.lower():
            return c
    return None

# ================= 6. PERSISTENT ANTI-DUPLICATE LEDGER & MULTI-FEED CURATION =================
def _extract_rss_image(entry):
    for th in entry.findall(".//{http://search.yahoo.com/mrss/}thumbnail") + entry.findall(".//media:thumbnail", {"media": "http://search.yahoo.com/mrss/"}):
        u = th.attrib.get("url", "")
        if u: return upgrade_image_url(u)
    for enc in entry.findall("enclosure"):
        if "image" in enc.attrib.get("type", "").lower() and enc.attrib.get("url"):
            return upgrade_image_url(enc.attrib["url"])
    return ""

def _extract_keywords(text):
    words = re.findall(r"[a-zA-Z0-9]{2,}", (text or "").lower())
    important_short = {"xi", "uk", "un", "eu", "ai", "g7", "us"}
    return {w for w in words if (len(w) >= 3 or w in important_short) and w not in STOPWORDS}

def load_persistent_history():
    default_entries = [
        {"headline": "Trump Putin and Xi plan historic joint meeting in China APEC", "timestamp": "2026-11-15T05:00:00+00:00", "format": "long"},
        {"headline": "Microsoft deeply sorry for global outage cloud disruption", "timestamp": "2026-11-14T10:00:00+00:00", "format": "short"},
        {"headline": "Ukraine military Starlink disrupted drone power plant", "timestamp": "2026-11-14T08:00:00+00:00", "format": "short"}
    ]
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                entries = data.get("entries", [])
                return entries if entries else default_entries
        except Exception as e:
            logger.warning(f"History read fallback: {e}")
    return default_entries

def save_persistent_history(entries, new_headlines, video_format):
    os.makedirs(os.path.dirname(os.path.abspath(HISTORY_FILE)), exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    for hl in new_headlines:
        entries.insert(0, {"headline": hl, "timestamp": now_iso, "format": video_format})
    entries = entries[:120]
    with open(HISTORY_FILE, "w") as f:
        json.dump({"updated_at": now_iso, "entries": entries}, f, indent=2)

def _get_recent_channel_state():
    entries = load_persistent_history()
    recent_records = []
    latest_dt = None
    last_format = "long"

    if entries:
        last_format = entries[0].get("format", "long")

    for item in entries:
        hl = item.get("headline", "")
        ts = item.get("timestamp", "")
        if hl:
            recent_records.append(_extract_keywords(hl))
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
            except Exception: pass

    token = _get_youtube_token()
    if token:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true", headers=headers, timeout=6)
            if r.status_code == 200:
                uploads_id = r.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
                r2 = requests.get(f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults=25", headers=headers, timeout=6)
                if r2.status_code == 200:
                    for item in r2.json().get("items", []):
                        sn = item.get("snippet", {})
                        pub_str = sn.get("publishedAt", "")
                        title = sn.get("title", "")
                        if pub_str:
                            try:
                                dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                                if latest_dt is None or dt > latest_dt:
                                    latest_dt = dt
                            except Exception: pass
                        recent_records.append(_extract_keywords(title))
        except Exception: pass

    return recent_records, latest_dt, last_format, entries

def is_topic_already_covered(headline, recent_keyword_sets):
    hl_kw = _extract_keywords(headline)
    if not hl_kw: return False
    for r_kw in recent_keyword_sets:
        overlap = hl_kw.intersection(r_kw)
        if len(overlap) >= 2:
            return True
    return False

def fetch_high_viral_international_news(max_stories=6, recent_keyword_sets=None):
    feeds = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
        "https://www.theguardian.com/world/rss",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"
    ]
    recent_keyword_sets = recent_keyword_sets or []
    candidates = []
    seen_titles = set()

    for fu in feeds:
        try:
            r = requests.get(fu, headers=HEADERS, timeout=6)
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:25]:
                title = _clean_text(item.findtext("title", ""))
                title = re.sub(r"\s*-\s*([A-Za-z0-9\s\.]+)$", "", title).strip()
                if not title or len(title) < 15 or title.lower() in seen_titles: continue
                seen_titles.add(title.lower())

                desc = _clean_text(item.findtext("description", ""))
                desc = re.sub(r"\s*-\s*(BBC News|Reuters|The Guardian|AP|Associated Press|Al Jazeera|CNN|CNBC)$", "", desc, flags=re.IGNORECASE)
                v_score = score_story_virality(title, desc)
                if v_score < 15:
                    continue

                link = item.findtext("link", "").strip()
                img_url = _extract_rss_image(item)
                cat = classify_headline_topic(f"{title} {desc}")
                candidates.append({
                    "headline": title, "summary": desc or title,
                    "article_url": link, "image_url": img_url,
                    "category": cat, "viral_score": v_score
                })
        except Exception: pass

    candidates.sort(key=lambda x: x["viral_score"], reverse=True)

    selected = []
    active_topic_sets = list(recent_keyword_sets)
    for st in candidates:
        if is_topic_already_covered(st["headline"], active_topic_sets):
            continue
        selected.append(st)
        active_topic_sets.append(_extract_keywords(st["headline"]))
        if len(selected) >= max_stories:
            break

    return selected

# ================= 7. DEEP EDITORIAL SCRIPTWRITER (5M & 10M DURATION CONTROL) =================
def humanize_english_anchor_speech(headline, summary, index, total, mode="STANDARD_BULLETIN"):
    hooks = [
        "Breaking global developments tonight.",
        "Turning now to major international security updates.",
        "In a significant shift impacting global markets,",
        "Meanwhile, in high-stakes international diplomacy,",
        "In strategic defense and intelligence news,",
        "Across the global economy today,"
    ]
    hook = hooks[index % len(hooks)]
    clean_s = summary if (len(summary.split()) >= 12 and "<" not in summary) else f"{headline}. Senior international officials and market analysts are closely tracking the immediate fallout."

    if mode == "VIRAL_SHORT":
        return (
            f"Urgent breaking report. {headline}. {clean_s} "
            f"Intelligence and geopolitical analysts warn this critical development could trigger immediate international repercussions across major capitals. "
            f"Stay with {CHANNEL_NAME} as we track the global fallout."
        )
    elif mode == "PRIME_DOCUMENTARY":
        return (
            f"{hook} {headline}. {clean_s} "
            f"Behind the headlines, diplomatic and defense observers point out that this event represents a pivotal turning point in international relations. "
            f"Key stakeholders in Washington, Brussels, and across the Indo-Pacific are already recalibrating their strategic posture in response. "
            f"Furthermore, market strategists warn that supply chains, energy security, and regional alliances could experience substantial pressure over the coming weeks as authorities prepare their next move."
        )
    else:
        return (
            f"{hook} {headline}. {clean_s} "
            f"Strategic analysts emphasize that this development carries far-reaching consequences for international stability, diplomatic alliances, and global markets. "
            f"Officials across major capitals are preparing coordinated responses as the situation continues to unfold."
        )

def _call_gemini_with_fallback(prompt):
    if not GEMINI_API_KEY: return None
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception as e:
            logger.warning(f"Gemini model {model_name} notice: {e}")
            time.sleep(1)
    return None

def polish_english_bulletin_with_gemini(stories, edition_title, mode="STANDARD_BULLETIN"):
    """
    Controls exact spoken word counts per story to hit target video lengths:
    - VIRAL_SHORT: ~85 words (38-45 seconds total Short)
    - BREAKING_FLASH: ~140 words per story x 3 stories (~3 minutes)
    - STANDARD_BULLETIN: ~125 words per story x 6 stories (~5.5 minutes)
    - PRIME_DOCUMENTARY: ~165 words per story x 8 stories (~8.5 to 10 minutes -> Mid-Roll Ad Revenue!)
    """
    word_target = 85 if mode == "VIRAL_SHORT" else (165 if mode == "PRIME_DOCUMENTARY" else 125)
    prompt = f"""You are the Chief International Broadcast Editor for '{CHANNEL_NAME}' (style of WION, BBC World, DW News).
Write high-retention spoken television news scripts and on-screen intelligence cards for these {len(stories)} stories.
Broadcast Format: {mode} ({edition_title})

CRITICAL MONETIZATION & DURATION REQUIREMENTS:
1. Spoken Copy Length: Each story's `spoken_copy` MUST be approximately {word_target} words ({word_target - 15} to {word_target + 20} words) of rich, authoritative journalism:
   - Part 1: Urgent opening hook & core verified facts.
   - Part 2: Deep background context & international reaction.
   - Part 3: Strategic geopolitical or economic impact ("Why this matters globally").
2. Also provide a 1-sentence `key_fact` (under 18 words) and a 1-sentence `why_it_matters` (under 18 words) for our on-screen television graphics.

Return ONLY valid JSON:
{{
  "bulletin": [
    {{
      "headline": "...",
      "spoken_copy": "...",
      "key_fact": "...",
      "why_it_matters": "..."
    }}
  ]
}}

Stories:
""" + "\n".join([f"{i+1}. [{s['category']}] {s['headline']} - {s['summary']}" for i, s in enumerate(stories)])

    raw = _call_gemini_with_fallback(prompt)
    if raw:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m: return json.loads(m.group(0)).get("bulletin")
        except Exception: pass
    return None

def synthesize_broadcast_voice(text, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    voice = "en-GB-SoniaNeural" if gender.lower() == "female" else "en-GB-RyanNeural"
    for attempt in range(2):
        cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", output_path]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return output_path
        time.sleep(1)
    try:
        from gtts import gTTS
        gTTS(text=text, lang="en", tld="co.uk", slow=False).save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return output_path
    except Exception: pass
    create_silence_wav(6.0, output_path)
    return output_path

def create_silence_wav(duration=0.4, output_path="temp/silence.wav"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(duration), output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def _get_audio_duration(path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        out = subprocess.check_output(cmd).decode().strip()
        return max(1.5, float(out))
    except Exception: return 6.0

def generate_pro_broadcast_bed(duration, output_path="temp/broadcast_bed.wav"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    filter_expr = (
        f"aevalsrc=sin(2*PI*58*t)*exp(-3*mod(t\\,0.5))"
        f"+0.08*sin(2*PI*1200*t)*exp(-30*mod(t\\,0.5))"
        f"+0.04*sin(2*PI*220*t):s=24000:d={duration}"
    )
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", filter_expr, output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def split_spoken_into_caption_chunks(spoken_text, num_chunks=6):
    words = (spoken_text or "").split()
    if not words: return [""]
    chunk_size = max(4, math.ceil(len(words) / max(1, num_chunks)))
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

# ================= 8. DUAL-ANCHOR VIDEO RENDERER (16:9 & 9:16) =================
def build_news_video(edition_label, scene_assets, output_path, is_short=True):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    W, H = (1080, 1920) if is_short else (1920, 1080)
    fps = 20
    anc_w, anc_h = (1080, 842) if is_short else (760, 928)

    # Load BOTH Male and Female studio anchors for dynamic co-hosting!
    female_vid = find_real_anchor_video("female")
    male_vid = find_real_anchor_video("male")
    anchors = {
        "female": RealStudioAnchor(female_vid, target_w=anc_w, target_h=anc_h) if female_vid else None,
        "male": RealStudioAnchor(male_vid, target_w=anc_w, target_h=anc_h) if male_vid else None
    }

    silence_pause = create_silence_wav(0.45, "temp/pause.wav")
    silence_outro = create_silence_wav(0.45, "temp/outro.wav")
    concat_list = "temp/audio_concat.txt"
    with open(concat_list, "w") as f:
        for idx, sc in enumerate(scene_assets):
            f.write(f"file '{os.path.abspath(sc['audio_path'])}'\n")
            if idx < len(scene_assets) - 1: f.write(f"file '{os.path.abspath(silence_pause)}'\n")
        f.write(f"file '{os.path.abspath(silence_outro)}'\n")

    merged_voice = "temp/merged_voice.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, merged_voice], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total_dur = _get_audio_duration(merged_voice)
    bgm_path = generate_pro_broadcast_bed(total_dur)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", merged_voice, "-i", bgm_path,
        "-filter_complex", "[1:a]highpass=f=75,treble=g=1.5:f=4500,loudnorm=I=-13:LRA=7:TP=-1.0[voice];[2:a]volume=0.07[bgm];[voice][bgm]amix=inputs=2:weights=1.0 0.12:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", output_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    global_frame = 0
    total_expected_frames = max(1, int(total_dur * fps))
    ticker_text = f"  ★★★  {CHANNEL_NAME}  |  {edition_label}  ★★★  " + "  |  ".join([sc["headline"] for sc in scene_assets]) + "  ★★★  "

    card_w, card_h = (1080, 830) if is_short else (1160, 928)

    for sc_idx, sc in enumerate(scene_assets):
        speech_dur = sc.get("duration", 6.0)
        pause_dur = 0.45
        speech_frames = max(1, int(speech_dur * fps))
        pause_frames = max(1, int(pause_dur * fps))
        total_scene_frames = speech_frames + pause_frames
        raw_photo = Image.open(sc["image_path"]).convert("RGB")
        is_outro_scene = (sc.get("category") == "NETWORK")
        caption_chunks = split_spoken_into_caption_chunks(sc.get("spoken_text", ""), num_chunks=max(2, int(speech_dur / 2.2)))

        sc_gender = sc.get("anchor_gender", "female").lower()
        active_anchor = anchors.get(sc_gender) or anchors.get("female") or anchors.get("male")

        for f_idx in range(total_scene_frames):
            is_speaking = (f_idx < speech_frames)
            prog = f_idx / float(max(1, total_scene_frames))
            chunk_idx = min(len(caption_chunks) - 1, int(prog * len(caption_chunks)))
            cur_caption = caption_chunks[chunk_idx] if (is_speaking and not is_outro_scene) else ""

            if is_outro_scene:
                story_card = raw_photo.resize((card_w, card_h), Image.Resampling.LANCZOS)
                od = ImageDraw.Draw(story_card)
                pad = 40
                box_w, box_h = card_w - (pad * 2), card_h - 160
                od.rectangle([pad, 80, pad + box_w, 80 + box_h], fill=(12, 22, 54), outline=(255, 215, 0), width=3)
                od.text((pad + 36, 120), "STAY INFORMED. STAY AHEAD.", font=_get_font(38 if card_w >= 1000 else 30, bold=True), fill=(255, 255, 255))
                od.rectangle([pad + 36, 200, pad + box_w - 36, 272], fill=(185, 14, 28))
                od.text((pad + 52, 222), "★ LIKE  •  SUBSCRIBE  •  COMMENT  •  SHARE ★", font=_get_font(24, bold=True), fill=(255, 255, 255))
                od.text((pad + 36, 310), "What are your thoughts on today's report?", font=_get_font(24, bold=True), fill=(255, 215, 0))
                od.text((pad + 36, 355), "Share your perspective in the comments below!", font=_get_font(22), fill=(220, 230, 245))
                od.text((pad + 36, 415), "Official Channel: @nexoranewsworld", font=_get_font(24, bold=True), fill=(255, 255, 255))
            else:
                story_card = render_animated_story_card(
                    raw_photo, sc, target_w=card_w, target_h=card_h,
                    progress_ratio=prog, caption_chunk=cur_caption, is_short=is_short
                )

            frame_img = Image.new("RGB", (W, H), (10, 16, 36))
            anc_frame = active_anchor.get_frame(global_frame, is_speaking=is_speaking) if active_anchor else None

            if is_short:
                frame_img.paste(story_card, (0, 104))
                if anc_frame: frame_img.paste(anc_frame, (0, 998))
                top_bar = Image.new("RGB", (W, 104), (185, 14, 28))
                tb_draw = ImageDraw.Draw(top_bar)
                tb_draw.ellipse([24, 38, 44, 58], fill=(255, 255, 255))
                tb_draw.text((54, 34), f"{CHANNEL_NAME}  |  GLOBAL LIVE", font=_get_font(28, bold=True), fill=(255, 255, 255))
                tb_draw.text((W - 170, 36), datetime.now(timezone.utc).strftime("%H:%M UTC"), font=_get_font(26, bold=True), fill=(255, 215, 0))
                frame_img.paste(top_bar, (0, 0))
                div_bar = Image.new("RGB", (W, 64), (12, 22, 54))
                dd = ImageDraw.Draw(div_bar)
                dd.line([(0, 0), (W, 0)], fill=(255, 215, 0), width=3)
                dd.text((36, 18), f"● {sc.get('category', 'WORLD')} SPECIAL REPORT", font=_get_font(22, bold=True), fill=(255, 215, 0))
                bar_w = int(W * min(1.0, global_frame / float(total_expected_frames)))
                dd.rectangle([0, 58, bar_w, 64], fill=(235, 20, 36))
                frame_img.paste(div_bar, (0, 934))
                
                tick = Image.new("RGB", (W, 80), (8, 12, 24))
                td = ImageDraw.Draw(tick)
                td.line([(0, 0), (W, 0)], fill=(185, 14, 28), width=3)
                text_pixel_width = max(len(ticker_text) * 14, 800)
                shift = (global_frame * 5) % text_pixel_width
                td.text((W - shift, 26), ticker_text + "  " + ticker_text, font=_get_font(22, bold=True), fill=(240, 240, 240))
                td.rectangle([0, 0, 150, 80], fill=(185, 14, 28))
                td.rectangle([150, 0, 154, 80], fill=(255, 215, 0))
                td.text((20, 26), "LATEST", font=_get_font(22, bold=True), fill=(255, 255, 255))
                frame_img.paste(tick, (0, H - 80))
            else:
                if anc_frame: frame_img.paste(anc_frame, (0, 76))
                frame_img.paste(story_card, (760, 76))
                dline = ImageDraw.Draw(frame_img)
                dline.line([(760, 76), (760, 1004)], fill=(185, 14, 28), width=4)
                dline.line([(764, 76), (764, 1004)], fill=(255, 215, 0), width=2)
                hdr = Image.new("RGB", (W, 76), (12, 22, 54))
                hd = ImageDraw.Draw(hdr)
                hd.ellipse([26, 28, 46, 48], fill=(235, 20, 36))
                hd.text((56, 22), f"{CHANNEL_NAME} WORLDWIDE", font=_get_font(30, bold=True), fill=(255, 255, 255))
                hd.text((460, 26), f"{edition_label}  |  STORY {min(sc_idx+1, len(scene_assets)-1)} OF {max(1, len(scene_assets)-1)}", font=_get_font(20, bold=True), fill=(255, 215, 0))
                hd.text((W - 180, 24), datetime.now(timezone.utc).strftime("%H:%M UTC"), font=_get_font(24, bold=True), fill=(255, 255, 255))
                frame_img.paste(hdr, (0, 0))
                
                tick = Image.new("RGB", (W, 76), (8, 12, 24))
                td = ImageDraw.Draw(tick)
                td.line([(0, 0), (W, 0)], fill=(185, 14, 28), width=3)
                text_pixel_width = max(len(ticker_text) * 16, 1000)
                shift = (global_frame * 6) % text_pixel_width
                td.text((W - shift, 24), ticker_text + "  " + ticker_text, font=_get_font(24, bold=True), fill=(245, 245, 245))
                td.rectangle([0, 0, 190, 76], fill=(185, 14, 28))
                td.rectangle([190, 0, 194, 76], fill=(255, 215, 0))
                td.text((26, 24), "BREAKING", font=_get_font(24, bold=True), fill=(255, 255, 255))
                frame_img.paste(tick, (0, H - 76))

            proc.stdin.write(frame_img.tobytes())
            global_frame += 1

    proc.stdin.close()
    proc.wait()
    logger.info(f"Broadcast video rendered ({total_dur/60.0:.2f} mins): {output_path}")
    return output_path

# ================= 9. THUMBNAIL, SEO, PLAYLIST & AUTO-COMMENT ENGINE =================
def generate_broadcast_thumbnail(headline, category, base_img_path, output_path, badge_text="BREAKING NEWS"):
    card = Image.open(base_img_path).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(720):
        if y > 220: odraw.line([(0, y), (1280, y)], fill=(6, 10, 24, int(248 * ((y - 220) / 500))))
    card.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(card)
    bw = max(360, len(badge_text) * 20 + 60)
    draw.rectangle([40, 40, 40 + bw, 102], fill=(185, 14, 28))
    draw.rectangle([40 + bw, 40, 48 + bw, 102], fill=(255, 215, 0))
    draw.text((58, 55), f"● {badge_text}", font=_get_font(28, bold=True), fill=(255, 255, 255))
    font_th = _get_font(52, bold=True)
    wrapped = wrap_text_to_width(headline.upper(), font_th, 1180, max_lines=2)
    y_pos = 465
    for line in wrapped:
        draw.text((44, y_pos + 4), line, font=font_th, fill=(0, 0, 0))
        draw.text((40, y_pos), line, font=font_th, fill=(255, 215, 0))
        y_pos += 64
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    card.save(output_path, quality=95)
    return output_path

def _sanitize_title(title, is_short=False):
    t = _clean_text(title)
    t = re.sub(r"[<>]", "", t)
    max_len = 76 if is_short else 88
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0]
    if is_short and "#Shorts" not in t:
        t = f"{t} #Shorts"
    return t[:95].strip()

def build_chapter_timestamps(scene_assets):
    lines = ["00:00 🔴 Lead Breaking Report"]
    elapsed = 0.0
    for idx, sc in enumerate(scene_assets[:-1]):
        if idx > 0:
            mm = int(elapsed // 60)
            ss = int(elapsed % 60)
            lines.append(f"{mm:02d}:{ss:02d} 🌐 {sc['headline'][:62]}")
        elapsed += sc.get("duration", 6.0) + 0.45
    return "\n".join(lines)

def generate_viral_metadata(story, edition_title, is_short=False, chapter_block="", mode="STANDARD_BULLETIN"):
    headline = story.get("headline", "").strip()
    summary = story.get("summary", "").strip()
    category = story.get("category", "WORLD").upper()
    debate_q = f"🔥 QUESTION OF THE DAY: What is your take on '{headline}'? Share your perspective below! 👇"

    prompt = f'''You are the Head of YouTube Growth & Monetization for '{CHANNEL_NAME}' (WION / BBC World style).
Create ultra-high CTR viral metadata and a viewer debate question for this news broadcast:
Lead Headline: "{headline}"
Summary: "{summary}"
Category: "{category}"
Broadcast Mode: {mode}
Format: {"YouTube Shorts (under 72 chars, urgent curiosity hook, ending with #Shorts)" if is_short else "YouTube Long Video (under 86 chars, high-stakes television headline)"}

Return ONLY valid JSON:
{{
  "title": "...",
  "description": "...",
  "tags": ["WorldNews", "BreakingNews", "Geopolitics", ...],
  "debate_question": "🔥 QUESTION OF THE DAY: ...?"
}}'''
    raw = _call_gemini_with_fallback(prompt)
    if raw:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                title = _sanitize_title(data.get("title", headline), is_short=is_short)
                desc = re.sub(r"[<>]", "", data.get("description", summary))
                if chapter_block and not is_short:
                    desc = f"{desc}\n\n⏱️ FULL BROADCAST CHAPTERS:\n{chapter_block}"
                tags = data.get("tags", ["WorldNews", "BreakingNews", "Geopolitics"])
                debate_q = data.get("debate_question", debate_q)
                return title, desc, tags[:15], debate_q
        except Exception: pass

    clean_h = headline
    for p in ["BREAKING:", "ALERT:", "WARNING:", "JUST IN:"]:
        clean_h = clean_h.replace(p, "").strip()

    if is_short:
        title = _sanitize_title(f"⚡ JUST IN: {clean_h}", is_short=True)
    elif mode == "PRIME_DOCUMENTARY":
        title = _sanitize_title(f"🚨 SPECIAL REPORT: {clean_h} | {CHANNEL_NAME}", is_short=False)
    else:
        title = _sanitize_title(f"🚨 BREAKING: {clean_h} | {CHANNEL_NAME}", is_short=False)

    tags = [
        "BreakingNews", "WorldNews", "Geopolitics", "InternationalNews", "GlobalNews",
        "USNews", "LiveNews", "WorldAffairs", "DefenseNews", "GlobalEconomy", "NexoraNews"
    ]
    if is_short:
        tags.extend(["Shorts", "NewsShorts", "ViralShorts"])
    words = [w.capitalize() for w in re.sub(r'[^a-zA-Z0-9\s]', '', headline).split() if len(w) > 4]
    tags.extend(words[:4])

    chapters_txt = f"\n\n⏱️ FULL BROADCAST CHAPTERS:\n{chapter_block}" if (chapter_block and not is_short) else ""
    desc = f'''{title}

🌍 GLOBAL SITUATION REPORT:
{summary}{chapters_txt}

💬 JOIN THE CONVERSATION:
What are your thoughts on today's developments? Leave a comment below!

🔔 Subscribe to @{CHANNEL_NAME.replace(" ", "").lower()}world for 24/7 verified global coverage and geopolitical analysis.

#BreakingNews #WorldNews #Geopolitics #GlobalNews #LiveNews #Shorts #NexoraNews'''
    return title, re.sub(r"[<>]", "", desc), tags[:15], debate_q

def _get_youtube_token():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        logger.error("❌ YouTube OAuth credentials missing! Check GitHub Secrets.")
        return None
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SECRET,
            "refresh_token": YT_REFRESH_TOKEN, "grant_type": "refresh_token"
        }, timeout=10)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        logger.error(f"❌ YouTube OAuth exception: {e}")
    return None

def post_engagement_comment(video_id, comment_text, token):
    if not video_id or not token: return
    try:
        url = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"
        payload = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {"textOriginal": comment_text}
                }
            }
        }
        r = requests.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=10)
        if r.status_code in (200, 201):
            logger.info(f"💬 Auto-posted engagement comment on video {video_id}")
    except Exception: pass

def upload_to_youtube(video_path, title, description, tags, thumbnail_path=None, is_short=False, comment_hook=None):
    token = _get_youtube_token()
    if not token: return None
    if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000: return None

    file_size = os.path.getsize(video_path)
    safe_title = _sanitize_title(title, is_short=is_short)
    video_type_str = "SHORTS" if is_short else "LONG BROADCAST"
    logger.info(f"Initiating YouTube Upload [{video_type_str}] ({file_size / (1024*1024):.2f} MB): {safe_title}")

    for attempt in range(1, 4):
        try:
            init_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4"
            }
            meta = {
                "snippet": {
                    "title": safe_title,
                    "description": description[:4500],
                    "tags": [t[:30] for t in tags[:15]],
                    "categoryId": "25",
                    "defaultLanguage": "en",
                    "defaultAudioLanguage": "en"
                },
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
            }
            res = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", headers=init_headers, json=meta, timeout=15)
            if res.status_code not in (200, 201):
                logger.error(f"❌ Init Error (Attempt {attempt}/3 - HTTP {res.status_code}): {res.text}")
                if "quotaExceeded" in res.text or "uploadLimitExceeded" in res.text:
                    logger.error("⚠️ YouTube Daily Upload Quota reached! Stopping retries until quota resets.")
                    return None
                time.sleep(4)
                continue

            upload_url = res.headers.get("Location")
            if not upload_url:
                time.sleep(4)
                continue

            put_headers = {"Content-Type": "video/mp4", "Content-Length": str(file_size)}
            with open(video_path, "rb") as f:
                v_res = requests.put(upload_url, headers=put_headers, data=f, timeout=450)

            if v_res.status_code in (200, 201):
                vid_id = v_res.json().get("id")
                logger.info(f"✅ Uploaded {video_type_str}: https://youtu.be/{vid_id}")
                if vid_id and thumbnail_path and os.path.exists(thumbnail_path):
                    try:
                        thumb_size = os.path.getsize(thumbnail_path)
                        with open(thumbnail_path, "rb") as tf:
                            requests.post(
                                f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}",
                                headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg", "Content-Length": str(thumb_size)},
                                data=tf, timeout=20
                            )
                    except Exception: pass
                if vid_id and comment_hook:
                    post_engagement_comment(vid_id, comment_hook, token)
                return vid_id
            else:
                logger.error(f"❌ Upload Error (Attempt {attempt}/3 - HTTP {v_res.status_code}): {v_res.text}")
                time.sleep(5)
        except Exception as e:
            logger.error(f"❌ Upload exception on attempt {attempt}: {e}")
            time.sleep(5)
    return None

# ================= 10. MASTER ORCHESTRATOR & CLI =================
def produce_news_episode(video_type="auto", category="WORLD", edition="auto", anchor_gender="auto", skip_upload=False, breaking_check=False, force=False):
    utc_now = datetime.now(timezone.utc)
    recent_keyword_sets, latest_dt, last_format, history_entries = _get_recent_channel_state()

    # Pre-scan top stories to check if a Mega Breaking Event is happening right now
    candidate_stories = fetch_high_viral_international_news(max_stories=8, recent_keyword_sets=recent_keyword_sets)
    if not candidate_stories:
        logger.info("No fresh uncovered high-impact stories detected right now. Cycle complete.")
        return

    lead_story = candidate_stories[0]
    lead_score = lead_story.get("viral_score", 20)
    is_mega_breaking = (lead_score >= 85)

    # Smart Cooldown Check (1.0h for Mega Breaking News, 2.8h for regular schedule)
    if breaking_check and not force and latest_dt is not None:
        hours_since = (utc_now - latest_dt).total_seconds() / 3600.0
        req_cooldown = BREAKING_COOLDOWN_HOURS if is_mega_breaking else NORMAL_COOLDOWN_HOURS
        if hours_since < req_cooldown:
            logger.info(f"⏳ Cooldown active ({hours_since:.2f}h < {req_cooldown}h | Lead Score: {lead_score}). Waiting for next slot.")
            return

    mode_name, is_short_mode, stories_count, edition_label = select_optimal_broadcast_mode(
        utc_now.hour, last_format, lead_score, requested_type=video_type
    )
    stories = candidate_stories[:stories_count]

    logger.info(f"🚀 Launching [{mode_name}] ({stories_count} stories) | Lead (Score {lead_score}): {lead_story['headline']}")

    polished = polish_english_bulletin_with_gemini(stories, edition_label, mode=mode_name)
    scene_assets = []
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    card_w, card_h = (1080, 830) if is_short_mode else (1160, 928)

    for idx, st in enumerate(stories):
        # Co-Anchor Alternating System: Alternate Female & Male anchors across stories in Long Broadcasts!
        if anchor_gender == "auto":
            story_anchor = "female" if ((utc_now.hour + idx) % 2 == 0) else "male"
        else:
            story_anchor = anchor_gender

        p_item = polished[idx] if (polished and idx < len(polished) and isinstance(polished[idx], dict)) else {}
        spoken = p_item.get("spoken_copy") or humanize_english_anchor_speech(st["headline"], st["summary"], idx, len(stories), mode=mode_name)
        key_fact = p_item.get("key_fact") or st["summary"][:110]
        why_matters = p_item.get("why_it_matters") or "Global analysts warn this development could reshape regional security and international market stability."

        raw_path = f"temp/raw_{idx}.jpg"
        download_raw_scene_photo(st, raw_path, target_w=card_w, target_h=card_h)
        aud_path = f"temp/voice_{idx}.mp3"
        synthesize_broadcast_voice(spoken, aud_path, gender=story_anchor)
        dur = _get_audio_duration(aud_path)
        scene_assets.append({
            "headline": st["headline"],
            "category": st["category"],
            "image_path": raw_path,
            "audio_path": aud_path,
            "duration": dur,
            "spoken_text": spoken,
            "key_fact": key_fact,
            "why_it_matters": why_matters,
            "anchor_gender": story_anchor
        })

    lead_headline = lead_story["headline"]
    outro_anchor = scene_assets[0]["anchor_gender"]

    if not is_short_mode:
        logger.info(f"=== RENDERING 16:9 {mode_name} ({len(scene_assets)} STORIES) ===")
        outro_spoken_long = f"That concludes this {edition_label.lower()} of {CHANNEL_NAME}. What is your perspective on today's global developments? Share your thoughts in the comments below, and don't forget to like and subscribe for 24/7 verified coverage."
        outro_card_long = "temp/card_outro_long.jpg"
        create_broadcast_outro_card(output_path=outro_card_long, target_w=1160, target_h=928, studio_bg_path=STUDIO_BG_PATH, is_short=False)
        outro_aud_long = "temp/voice_outro_long.mp3"
        synthesize_broadcast_voice(outro_spoken_long, outro_aud_long, gender=outro_anchor)

        long_assets = list(scene_assets) + [{
            "headline": "LIKE & SUBSCRIBE TO NEXORA NEWS", "category": "NETWORK",
            "image_path": outro_card_long, "audio_path": outro_aud_long,
            "duration": _get_audio_duration(outro_aud_long), "spoken_text": outro_spoken_long,
            "anchor_gender": outro_anchor
        }]
        long_out = "output/NEXORA_NEWS_BROADCAST.mp4"
        build_news_video(edition_label, long_assets, long_out, is_short=False)
        thumb_out = "output/thumbnail.jpg"
        badge_txt = "SPECIAL REPORT" if mode_name == "PRIME_DOCUMENTARY" else ("URGENT FLASH" if mode_name == "BREAKING_FLASH" else "BREAKING NEWS")
        generate_broadcast_thumbnail(lead_headline, lead_story["category"], scene_assets[0]["image_path"], thumb_out, badge_text=badge_txt)
        if not skip_upload:
            chapters = build_chapter_timestamps(long_assets)
            v_title, v_desc, v_tags, debate_q = generate_viral_metadata(lead_story, edition_label, is_short=False, chapter_block=chapters, mode=mode_name)
            vid_id = upload_to_youtube(long_out, v_title, v_desc, v_tags, thumbnail_path=thumb_out, is_short=False, comment_hook=debate_q)
            if vid_id:
                save_persistent_history(history_entries, [s["headline"] for s in stories], "long")
    else:
        logger.info("=== RENDERING 9:16 VIRAL SHORT (40-50 SEC) ===")
        outro_spoken_short = f"What do you think about this? Drop your thoughts in the comments, and subscribe to {CHANNEL_NAME} for instant global alerts."
        outro_card_short = "temp/card_outro_short.jpg"
        create_broadcast_outro_card(output_path=outro_card_short, target_w=1080, target_h=830, studio_bg_path=STUDIO_BG_PATH, is_short=True)
        outro_aud_short = "temp/voice_outro_short.mp3"
        synthesize_broadcast_voice(outro_spoken_short, outro_aud_short, gender=outro_anchor)

        short_assets = [
            scene_assets[0],
            {
                "headline": "LIKE & SUBSCRIBE TO NEXORA NEWS", "category": "NETWORK",
                "image_path": outro_card_short, "audio_path": outro_aud_short,
                "duration": _get_audio_duration(outro_aud_short), "spoken_text": outro_spoken_short,
                "anchor_gender": outro_anchor
            }
        ]
        short_out = "output/NEXORA_NEWS_SHORT.mp4"
        build_news_video(edition_label, short_assets, short_out, is_short=True)
        if not skip_upload:
            v_title, v_desc, v_tags, debate_q = generate_viral_metadata(lead_story, edition_label, is_short=True, mode=mode_name)
            vid_id = upload_to_youtube(short_out, v_title, v_desc, v_tags, is_short=True, comment_hook=debate_q)
            if vid_id:
                save_persistent_history(history_entries, [lead_headline], "short")

    logger.info("Broadcast generation and production complete.")

def main():
    p = argparse.ArgumentParser(description="Nexora News v6.0 Complete Autonomous Network Engine")
    p.add_argument("--once", action="store_true", help="Run single broadcast cycle")
    p.add_argument("--type", choices=["auto", "both", "short", "long"], default="auto")
    p.add_argument("--category", default="WORLD")
    p.add_argument("--edition", default="auto")
    p.add_argument("--anchor", choices=["male", "female", "auto"], default="auto")
    p.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    p.add_argument("--breaking-check", action="store_true", help="Smart cooldown + emergency breaking override")
    p.add_argument("--force", action="store_true", help="Bypass cooldown for manual runs")
    args = p.parse_args()

    produce_news_episode(
        video_type=args.type, category=args.category, edition=args.edition,
        anchor_gender=args.anchor, skip_upload=args.skip_upload,
        breaking_check=args.breaking_check, force=args.force
    )

if __name__ == "__main__":
    main()
