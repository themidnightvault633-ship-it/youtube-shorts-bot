#!/usr/bin/env python3
"""
24/7 Autonomous AI TV News Network Engine (Professional Red Team Edition)
Features:
- Real Anchor Video Engine (Zero-Watermark Crop + Audio-Cadence Lipsync)
- Authentic Ground Photo Engine (Publisher og:image + Press Commons)
- 3-Tier Broadcast Aston (Location Kicker, Glassmorphic Strap, Live Pill)
- Sound Design: 120-BPM Newsroom Pulse Bed + EBU R128 (-14 LUFS) Mastering
- Automated Clickable 1280x720 YouTube Thumbnail Generator & API Uploader
- YouTube Analytics Feedback Loop (Auto-Prioritizes Winning Topics)
"""

import os, sys, re, glob, json, time, math, random, asyncio, logging, argparse, subprocess, urllib.parse, wave
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("NewsBot")

# ================= 1. CONFIG & CREDENTIALS =================
def _clean(v): return (v or "").strip().strip('"').strip("'").strip()
GEMINI_API_KEY = _clean(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean(os.environ.get("YT_REFRESH_TOKEN", ""))

CHANNEL_NAME = "BHARAT 24"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
TOPIC_ANALYTICS_FILE = os.path.join("assets", "topic_analytics.json")

TOPIC_TAXONOMY = {
    "DEFENSE_SECURITY": ["सेना", "बॉर्डर", "मिसाइल", "चीन", "पाकिस्तान", "युद्ध", "राफेल", "drdo", "आर्मी", "नेवी", "एयरफोर्स", "हमला", "सुरक्षा", "सैनिक", "defence"],
    "CRIME_LAW": ["पुलिस", "कोर्ट", "सीबीआई", "सुप्रीम कोर्ट", "गिरफ्तार", "एनकाउंटर", "जेल", "ईडी", "fir", "जांच", "हत्या", "हादसा", "कस्टडी", "मुठभेड़"],
    "POLITICS": ["मोदी", "संसद", "सरकार", "राहुल", "मंत्री", "cm", "bjp", "congress", "चुनाव", "पार्टी", "विपक्ष", "नेता", "कैबिनेट", "लोकसभा", "राज्यसभा"],
    "WORLD_GEOPOLITICS": ["अमेरिका", "ट्रंप", "रूस", "ईरान", "इजरायल", "गाजा", "संयुक्त राष्ट्र", "ग्लोबल", "विदेश", "यूक्रेन", "हूती", "पुतिन"],
    "SCIENCE_TECH": ["इसरो", "नासा", "अंतरिक्ष", "उपग्रह", "गगनयान", "चंद्रयान", "ai", "रोबोट", "5g", "स्मार्टफोन", "सेमीकंडक्टर", "tech"],
    "ECONOMY_FINANCE": ["शेयर बाजार", "सेंसेक्स", "बजट", "टैक्स", "बैंक", "सोना", "आरबीआई", "महंगाई", "लोन", "जीडीपी", "रुपया", "कारोबार"],
}

NEWS_FEEDS = {
    "NATION": [
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
        "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
        "https://www.amarujala.com/rss/breaking-news.xml",
        "https://ndtv.in/rss/top-stories",
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
    "MORNING": {"target_count": 100, "title_prefix": "🔴 LIVE महाबुलेटिन: Top 100 Superfast News", "counter_prefix": "ख़बर", "bulletin_label": "100 SUPERFAST"},
    "AFTERNOON": {"target_count": 16, "title_prefix": "🔴 LIVE दोपहर बुलेटिन: आज की बड़ी ख़बरें", "counter_prefix": "बड़ी ख़बर", "bulletin_label": "दोपहर बुलेटिन"},
    "EVENING": {"target_count": 50, "title_prefix": "🔴 LIVE शाम बुलेटिन: Top 50 Superfast News", "counter_prefix": "ख़बर", "bulletin_label": "TOP 50 NEWS"},
}

def get_current_edition():
    try:
        h = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).hour
        return "MORNING" if 5 <= h < 12 else ("AFTERNOON" if 12 <= h < 17 else "EVENING")
    except Exception:
        return "MORNING"

# ================= 2. TYPOGRAPHY ENGINE =================
def _get_devanagari_font(size=28):
    for p in ["assets/fonts/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def draw_text(draw, pos, text, size=28, fill=(255, 255, 255)):
    draw.text(pos, text, font=_get_devanagari_font(size), fill=fill)

def measure_text(draw, text, size=28):
    try:
        b = draw.textbbox((0, 0), text, font=_get_devanagari_font(size))
        return b[2] - b[0]
    except Exception:
        return len(text) * int(size * 0.58)

# ================= 3. TOPIC ANALYTICS & FEEDBACK =================
def classify_headline_topic(headline):
    hl = (headline or "").lower()
    sc = {t: sum(1 for kw in kws if kw in hl) for t, kws in TOPIC_TAXONOMY.items()}
    best = max(sc, key=sc.get)
    return best if sc[best] > 0 else "NATION_GENERAL"

def load_topic_analytics():
    if os.path.exists(TOPIC_ANALYTICS_FILE):
        try:
            with open(TOPIC_ANALYTICS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {"channel_stats": {"subscribers": 0, "total_views": 0, "video_count": 0}, "video_history": [], "recommended_topic": "DEFENSE_SECURITY"}

def save_topic_analytics(data):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(TOPIC_ANALYTICS_FILE)), exist_ok=True)
        with open(TOPIC_ANALYTICS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.warning(f"Could not save analytics: {e}")

def get_recommended_topic():
    rec = load_topic_analytics().get("recommended_topic")
    return rec if rec in TOPIC_TAXONOMY else "DEFENSE_SECURITY"

# ================= 4. GROUND PHOTO ENGINE =================
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
                if "1x1" not in u and "logo" not in u.lower():
                    ir = requests.get(u, headers=HEADERS, timeout=6)
                    if ir.status_code == 200 and len(ir.content) > 12000: return ir.content
    except Exception: pass
    return None

def _fetch_ground_news_photo(keywords, target_w, target_h):
    if not keywords: return None
    clean = re.sub(r"[^\w\s]", " ", keywords.replace("बड़ी खबर", "").replace("LIVE", "")).strip()
    words = [w for w in clean.split() if len(w) > 3][:4]
    if not words: return None
    try:
        p = {"action": "query", "generator": "search", "gsrsearch": " ".join(words), "gsrnamespace": "6", "gsrlimit": "2", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": str(target_w), "format": "json"}
        wr = requests.get("https://commons.wikimedia.org/w/api.php", params=p, headers=HEADERS, timeout=5)
        if wr.status_code == 200:
            for _, pdata in wr.json().get("query", {}).get("pages", {}).items():
                for info in pdata.get("imageinfo", []):
                    u = info.get("thumburl") or info.get("url")
                    if u and not u.endswith((".svg", ".ogg")):
                        ir = requests.get(u, headers=HEADERS, timeout=6)
                        if ir.status_code == 200 and len(ir.content) > 15000:
                            return _validate_image(ir.content, target_w, target_h)
    except Exception: pass
    return None

def _fetch_pollinations_image(prompt, target_w, target_h):
    try:
        clean = urllib.parse.quote(re.sub(r"[^\w\s,.-]", " ", prompt or "News photojournalism")[:180] + ", editorial news photo, 8k, no text")
        seed = random.randint(1000, 999999)
        r = requests.get(f"https://image.pollinations.ai/prompt/{clean}?width={768}&height={768}&seed={seed}&model=turbo&nologo=true", headers=HEADERS, timeout=8)
        if r.status_code == 200 and len(r.content) > 12000: return _validate_image(r.content, target_w, target_h)
    except Exception: pass
    return None

def create_broadcast_story_card(output_path, target_w=1100, target_h=740, headline="", counter="ख़बर 1", category="राष्ट्रीय", location="नई दिल्ली", bulletin="LIVE", base_img=None, is_short=False):
    if base_img is not None:
        img = base_img.copy()
    else:
        img = Image.new("RGB", (target_w, target_h), (12, 22, 54))
        draw_bg = ImageDraw.Draw(img)
        for y in range(target_h):
            ratio = y / float(target_h)
            draw_bg.line([(0, y), (target_w, y)], fill=(int(12 + 16 * ratio), int(24 + 36 * ratio), int(64 + 60 * ratio)))
        cx, cy = target_w // 2, int(target_h * 0.38)
        for rad in (90, 180, 290, 420): draw_bg.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(36, 80, 150), width=1)

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, target_w - 1, target_h - 1], outline=(70, 135, 215), width=4)
    draw.rectangle([4, 4, target_w - 5, target_h - 5], outline=(18, 38, 80), width=2)

    badge_str = f"🔴 {bulletin}  |  {counter}"
    bs = 22 if not is_short else 26
    bw = max(330 if not is_short else 410, measure_text(draw, badge_str, size=bs) + 38)
    draw.rounded_rectangle([18, 16, 18 + bw, 16 + (44 if not is_short else 54)], radius=8, fill=(195, 16, 32), outline=(255, 215, 0), width=2)
    draw_text(draw, (44, 22), badge_str, size=bs, fill=(255, 255, 255))

    ch_bug = f"{CHANNEL_NAME} EXCLUSIVE"
    cw = measure_text(draw, ch_bug, size=20) + 32
    draw.rounded_rectangle([target_w - cw - 18, 16, target_w - 18, 56], radius=6, fill=(10, 24, 52), outline=(0, 200, 255), width=2)
    draw_text(draw, (target_w - cw - 2, 22), ch_bug, size=20, fill=(0, 235, 255))

    box_h = 146 if not is_short else 180
    box_y = target_h - box_h - (16 if not is_short else 22)
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    ov = ImageDraw.Draw(overlay)
    ov.rounded_rectangle([16, box_y, target_w - 16, target_h - (16 if not is_short else 22)], radius=10, fill=(8, 14, 30, 242), outline=(250, 198, 0, 255), width=3)
    ov.rectangle([18, box_y + 2, target_w - 18, box_y + 6], fill=(225, 20, 36, 255))

    kicker = f" ● {location}  |  {category} "
    ks = 18 if not is_short else 22
    kw = measure_text(ov, kicker, size=ks) + 18
    ov.rounded_rectangle([28, box_y + 12, 28 + kw, box_y + 40], radius=6, fill=(195, 18, 34, 255))
    draw_text(ov, (36, box_y + 14), kicker, size=ks, fill=(255, 235, 80))

    words = (headline or "ताज़ा बड़ी ख़बर").strip().split()
    l1 = " ".join(words[:7 if not is_short else 6])
    l2 = " ".join(words[7 if not is_short else 6: 14 if not is_short else 12])
    draw_text(ov, (30, box_y + 50), l1, size=26 if not is_short else 31, fill=(255, 255, 255))
    if l2: draw_text(ov, (30, box_y + 90), l2, size=26 if not is_short else 31, fill=(255, 235, 75))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=95)
    return output_path

def download_scene_image(output_path, prompt="", rss_url="", article_url="", headline="", counter="", category="राष्ट्रीय", location="नई दिल्ली", bulletin="LIVE", is_short=True):
    tw, th = (1080, 830) if is_short else (1100, 740)
    base = None
    if rss_url and rss_url.startswith("http"):
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
    return create_broadcast_story_card(output_path, target_w=tw, target_h=th, headline_text=headline, counter_text=counter, category_tag=category, location_tag=location, bulletin_label=bulletin, base_img=base, is_short=is_short)

# ================= 5. REAL STUDIO ANCHOR VIDEO =================
class RealStudioAnchor:
    def __init__(self, video_path, target_w=760, target_h=900):
        self.w, self.h, self.frames = target_w, target_h, []
        try:
            p_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_path]
            fw, fh = [int(x) for x in subprocess.check_output(p_cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip().split("x")]
            cw = int(fh * (float(target_w) / float(target_h)))
            vf = f"crop={cw}:{fh}:{(fw - cw) // 2}:0,scale={target_w}:{target_h}:flags=lanczos"
            cmd = ["ffmpeg", "-v", "error", "-i", video_path, "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
            raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=40).stdout
            sz = target_w * target_h * 3
            for i in range(len(raw) // sz):
                self.frames.append(Image.fromarray(np.frombuffer(raw[i * sz: (i + 1) * sz], dtype=np.uint8).reshape((target_h, target_w, 3))))
            logger.info(f"✅ Loaded Real Anchor: {len(self.frames)} frames cached at {target_w}x{target_h}")
        except Exception as e: logger.warning(f"Could not load anchor: {e}")

    @property
    def total(self): return len(self.frames)

    def get_frame(self, frame_idx, viseme=0.5):
        if not self.frames:
            img = Image.new("RGB", (self.w, self.h), (18, 28, 64))
            draw_text(ImageDraw.Draw(img), (self.w // 2 - 120, self.h // 2), "🔴 LIVE STUDIO", size=36, fill=(255, 215, 0))
            return img
        return self.frames[(frame_idx + int(viseme * 10)) % len(self.frames)]

def find_real_anchor_video(gender="female"):
    for c in [f"assets/anchor_real_{gender}.mp4", f"assets/anchor_{gender}.mp4", f"anchor_real_{gender}.mp4", f"anchor_{gender}.mp4"]:
        if os.path.exists(c) and os.path.getsize(c) > 20000: return c
    return None

# ================= 6. LIVE RSS & STORY CURATION =================
def _extract_rss_image(item):
    for elem in item.iter():
        if elem.tag.lower().endswith(("content", "thumbnail", "enclosure")):
            u = elem.attrib.get("url") or elem.attrib.get("href")
            if u and u.startswith("http") and not u.endswith(".mp3"): return u
    for child in item:
        m = re.search(r'<img[^>]+src=[\'"](https?://[^\'"]+)[\'"]', child.text or "", re.IGNORECASE)
        if m: return m.group(1)
    return ""

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
                    title = re.sub(r"\s+-\s+[^-]+$", "", raw_t).strip() or raw_t
                    if len(title) < 10 or title.lower() in seen: continue
                    seen.add(title.lower())
                    headlines.append({
                        "title": title, "article_url": (it.findtext("link") or "").strip(),
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
    return headlines[:max_items]

# ================= 7. SOUND DESIGN & MASTERING =================
def synthesize_broadcast_voice(text, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    voice = "hi-IN-SwaraNeural" if gender == "female" else "hi-IN-MadhurNeural"
    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(text=text, voice=voice, rate="+3%").save(output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return output_path
    except Exception: pass
    try:
        from gtts import gTTS
        gTTS(text=text, lang="hi", slow=False).save(output_path)
    except Exception as e: logger.warning(f"Voice fallback error: {e}")
    return output_path

def _get_audio_duration(path):
    try: return max(2.0, float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], stderr=subprocess.DEVNULL, timeout=10).decode().strip()))
    except Exception: return 5.0

def _extract_audio_envelope(path, duration, fps=20):
    nf, sr = max(1, int(math.ceil(duration * fps)) + 2), 1200
    try:
        proc = subprocess.run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
        pcm = np.pad(np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32), (0, max(0, nf * (sr // fps) - len(proc.stdout) // 2)))[:nf * (sr // fps)]
        rms = np.sqrt(np.mean(pcm.reshape((nf, sr // fps)) ** 2, axis=1))
        return np.clip(rms / max(np.percentile(rms, 95) if rms.size > 0 else 1.0, 100.0), 0.0, 1.0)
    except Exception:
        return 0.45 + 0.45 * np.abs(np.sin(2.0 * np.pi * 3.8 * np.linspace(0, duration, nf)))

def generate_pro_broadcast_bed(duration, output_path="temp/broadcast_bed.wav", sr=22050):
    ns = int(duration * sr)
    t = np.linspace(0, duration, ns, endpoint=False)
    kick = np.sin(2 * np.pi * 65.0 * t) * np.exp(-12.0 * ((t % 0.5) / 0.5))
    tick = np.random.uniform(-0.1, 0.1, ns) * np.exp(-38.0 * ((t % 0.25) / 0.25))
    pad = (np.sin(2 * np.pi * 73.4 * t) * 0.35 + np.sin(2 * np.pi * 174.6 * t) * 0.18 + np.sin(2 * np.pi * 220.0 * t) * 0.15) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t))
    pcm = (np.clip((kick * 0.45 + tick * 0.15 + pad * 0.40) * 0.045, -0.9, 0.9) * 32767).astype(np.int16)
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

    concat_list = "temp/concat_audio.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for sc in scene_assets: f.write(f"file '{os.path.abspath(sc['audio_path'])}'\n")
    merged_voice = "temp/merged_voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", merged_voice], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bgm_path = generate_pro_broadcast_bed(_get_audio_duration(merged_voice))

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", merged_voice, "-i", bgm_path,
        "-filter_complex", "[1:a]loudnorm=I=-14:LRA=11:TP=-1.5[vnorm];[2:a]volume=0.18[bgm];[vnorm][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", output_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    global_frame = 0
    ticker_text = f"  ★★★  {CHANNEL_NAME} LIVE  ★★★  " + "  |  ".join([sc["headline"] for sc in scene_assets]) + "  ★★★  "

    for sc in scene_assets:
        n_frames = max(1, int(round(sc["duration"] * fps)))
        env = _extract_audio_envelope(sc["audio_path"], sc["duration"], fps=fps)
        story_card = Image.open(sc["image_path"]).convert("RGB")

        for f_i in range(n_frames):
            frame_img = Image.new("RGB", (W, H), (10, 16, 36))
            anc_frame = anchor_engine.get_frame(global_frame, float(env[min(f_i, len(env) - 1)])) if anchor_engine else None

            if is_short:
                frame_img.paste(story_card, (0, 0))
                div_bar = Image.new("RGB", (W, 90), (195, 16, 32))
                draw_text(ImageDraw.Draw(div_bar), (24, 24), f"🔴 {CHANNEL_NAME}  |  BREAKING NEWS SUPERFAST", size=32, fill=(255, 255, 255))
                frame_img.paste(div_bar, (0, 840))
                if anc_frame: frame_img.paste(anc_frame, (0, 934))
            else:
                hdr = Image.new("RGB", (W, 70), (12, 22, 54))
                h_draw = ImageDraw.Draw(hdr)
                draw_text(h_draw, (30, 16), f"🔴 {CHANNEL_NAME} LIVE  |  24/7 AUTONOMOUS NEWS NETWORK", size=26, fill=(255, 215, 0))
                draw_text(h_draw, (W - 200, 16), (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST"), size=24, fill=(255, 255, 255))
                frame_img.paste(hdr, (0, 0))

                if anc_frame: frame_img.paste(anc_frame, (20, 90))
                frame_img.paste(story_card.resize((1100, 740), Image.Resampling.LANCZOS), (790, 110))

                tick_bar = Image.new("RGB", (W, 76), (185, 14, 28))
                t_draw = ImageDraw.Draw(tick_bar)
                draw_text(t_draw, (180 - (global_frame * 6) % max(1, len(ticker_text) * 16), 22), ticker_text + ticker_text, size=25, fill=(255, 255, 255))
                t_draw.rectangle([0, 0, 170, 76], fill=(240, 185, 0))
                draw_text(t_draw, (16, 22), "🔴 ताज़ा सुर्खियां", size=24, fill=(0, 0, 0))
                frame_img.paste(tick_bar, (0, H - 76))

            proc.stdin.write(frame_img.tobytes())
            global_frame += 1

    proc.stdin.close()
    proc.wait()
    logger.info(f"🎬 Video complete: {output_path} ({os.path.getsize(output_path)/(1024*1024):.2f} MB)")
    return output_path

# ================= 9. THUMBNAIL & YOUTUBE =================
def generate_broadcast_thumbnail(headline, photo_path, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    TW, TH = 1280, 720
    base = Image.new("RGB", (TW, TH), (10, 16, 36))
    if photo_path and os.path.exists(photo_path):
        try: base.paste(_validate_image(open(photo_path, "rb").read(), 860, TH), (420, 0))
        except Exception: pass

    draw = ImageDraw.Draw(base)
    for x in range(TW):
        a = 1.0 if x < 480 else (1.0 - (x - 480) / 240.0 if x < 720 else 0.0)
        if a > 0: draw.line([(x, 0), (x, TH)], fill=(int(14 * a), int(22 * a), int(58 * a)))

    anc_vid = find_real_anchor_video(gender)
    if anc_vid:
        try:
            anc = RealStudioAnchor(anc_vid, target_w=480, target_h=TH)
            if anc.total > 0: base.paste(anc.get_frame(12), (0, 0))
        except Exception: pass

    draw.rectangle([0, 0, TW - 1, TH - 1], outline=(220, 20, 36), width=6)
    draw.rectangle([6, 6, TW - 7, TH - 7], outline=(255, 215, 0), width=2)
    draw.rounded_rectangle([30, 24, 380, 76], radius=8, fill=(210, 16, 30), outline=(255, 215, 0), width=2)
    draw_text(draw, (44, 30), f"🔴 {CHANNEL_NAME}  |  LIVE", size=32, fill=(255, 255, 255))

    draw.rectangle([20, TH - 220, TW - 20, TH - 24], fill=(8, 14, 28))
    draw.rectangle([20, TH - 224, TW - 20, TH - 218], fill=(255, 215, 0))
    w = (headline or "बड़ा फैसला! देश भर में अलर्ट").strip().split()
    draw_text(draw, (42, TH - 206), " ".join(w[:6]), size=48, fill=(0, 0, 0))
    draw_text(draw, (40, TH - 208), " ".join(w[:6]), size=48, fill=(255, 235, 60))
    if len(w) > 6:
        draw_text(draw, (42, TH - 138), " ".join(w[6:12]), size=44, fill=(0, 0, 0))
        draw_text(draw, (40, TH - 140), " ".join(w[6:12]), size=44, fill=(255, 255, 255))

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
                logger.info(f"📊 LIVE YOUTUBE: Subs: {adata['channel_stats']['subscribers']:,} | Views: {adata['channel_stats']['total_views']:,}")
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
    token = _get_youtube_token()
    if not token: return None
    safe_t = _sanitize_title(title, is_short=is_short)
    fsz = os.path.getsize(video_path)
    body = {"snippet": {"title": safe_t, "description": description[:4500], "tags": tags[:25], "categoryId": "25", "defaultLanguage": "hi"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    try:
        init_r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": str(fsz), "X-Upload-Content-Type": "video/mp4"}, json=body, timeout=30)
        up_url = init_r.headers.get("Location")
        if not up_url: return None
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
        if vid_id:
            logger.info(f"🎉 LIVE ON YOUTUBE: https://youtu.be/{vid_id}")
            if thumb_path and os.path.exists(thumb_path) and not is_short:
                try: requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}", headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}, data=open(thumb_path, "rb").read(), timeout=30)
                except Exception: pass
            return vid_id
    except Exception as e: logger.warning(f"Upload error: {e}")
    return None

# ================= 10. EPISODE ORCHESTRATOR =================
def produce_news_episode(category="AUTO", is_short=True, edition="auto", anchor_gender=None, skip_upload=False):
    ed = get_current_edition() if edition == "auto" else edition.upper()
    cfg = EDITION_CONFIGS.get(ed, EDITION_CONFIGS["MORNING"])
    headlines = fetch_trending_news(category=("NATION" if category == "AUTO" else category), max_items=(5 if is_short else cfg["target_count"]))
    gender = anchor_gender or ("female" if random.random() < 0.5 else "male")
    script = {"title": f"🔴 5 बड़ी ख़बरें! Top News Headlines #Shorts" if is_short else f"{cfg['title_prefix']} | {cfg['bulletin_label']}", "anchor_gender": gender}

    assets, lead_photo = [], None
    for idx, h in enumerate(headlines):
        sid = idx + 1
        img_p, aud_p = f"temp/scene_{sid}.jpg", f"temp/voice_{sid}.mp3"
        counter = f"ख़बर {sid} / {len(headlines)}" if not is_short else f"ख़बर {sid}"
        download_scene_image(img_p, prompt=h["title"], rss_url=h.get("media_url", ""), article_url=h.get("article_url", ""), headline=h["title"], counter=counter, category=h.get("category_tag", "राष्ट्रीय"), location=h.get("location_tag", "नई दिल्ली"), bulletin=cfg["bulletin_label"], is_short=is_short)
        if idx == 0 and os.path.exists(img_p): lead_photo = img_p
        synthesize_broadcast_voice(f"{h['title']}। {CHANNEL_NAME} पर इस बड़ी खबर की हर अपडेट हम आप तक पहुंचा रहे हैं।", aud_p, gender=gender)
        assets.append({"scene_id": sid, "image_path": img_p, "audio_path": aud_p, "headline": h["title"], "duration": _get_audio_duration(aud_p)})

    out = "final_short.mp4" if is_short else "final_long.mp4"
    build_news_video(script, assets, out, is_short=is_short)
    thumb = "temp/broadcast_thumb.jpg"
    if not is_short: generate_broadcast_thumbnail(headlines[0]["title"] if headlines else "आज की बड़ी खबरें", lead_photo, thumb, gender=gender)

    if not skip_upload:
        desc = f"{script['title']}\n\n📺 {CHANNEL_NAME} LIVE BROADCAST: देश और दुनिया की सभी बड़ी खबरें सीधे हमारे 24/7 न्यूज़ रूम से।\n\n📌 आज की प्रमुख खबरें:\n" + "\n".join([f"{i+1}. {sc['headline']}" for i, sc in enumerate(assets[:15])]) + "\n\n🔔 चैनल को Subscribe करें और Bell Icon दबाएं!"
        upload_to_youtube(out, script["title"], desc, [CHANNEL_NAME, "Hindi News", "Breaking News", "Superfast News"], thumb_path=thumb, is_short=is_short)
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--type", choices=["short", "long", "both"], default="both")
    p.add_argument("--edition", choices=["auto", "morning", "afternoon", "evening"], default="auto")
    p.add_argument("--category", default="AUTO")
    p.add_argument("--anchor", choices=["male", "female", "auto"], default="auto")
    p.add_argument("--skip-upload", action="store_true")
    p.add_argument("--check-youtube", action="store_true")
    args = p.parse_args()

    if args.check_youtube:
        tok = _get_youtube_token()
        if tok: logger.info("✅ YouTube OAuth2 Access Token Verified!"); sys.exit(0)
        logger.error("❌ YouTube Auth Check Failed"); sys.exit(1)

    if not args.skip_upload: sync_youtube_analytics()
    anc = None if args.anchor == "auto" else args.anchor
    if args.type in ("short", "both"): produce_news_episode(category=args.category, is_short=True, edition=args.edition, anchor_gender=anc, skip_upload=args.skip_upload)
    if args.type in ("long", "both"): produce_news_episode(category=args.category, is_short=False, edition=args.edition, anchor_gender=anc, skip_upload=args.skip_upload)

if __name__ == "__main__":
    main()
