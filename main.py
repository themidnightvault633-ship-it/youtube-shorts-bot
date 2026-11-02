#!/usr/bin/env python3
"""
NEXORA NEWS - 24/7 Autonomous International Broadcast Engine
High-definition automated video news channel with real anchor video looping,
1024p CDN photojournalism, 120-BPM heartbeat audio bed, and EBU R128 audio mastering.
"""
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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
TOPIC_ANALYTICS_FILE = os.path.join("assets", "topic_analytics.json")
LOGO_PATH = os.path.join("assets", "channel_logo.png")
STUDIO_BG_PATH = os.path.join("assets", "studio_background.jpg")

GLOBAL_TOPICS = {
    "GEOPOLITICS": ["united nations", "white house", "biden", "trump", "putin", "kremlin", "nato", "eu", "diplomacy", "summit", "sanctions", "china", "taiwan"],
    "DEFENSE_SECURITY": ["military", "pentagon", "defense", "missile", "navy", "warship", "fighter jet", "aircraft carrier", "army", "conflict", "security"],
    "GLOBAL_ECONOMY": ["federal reserve", "central bank", "inflation", "oil", "trade", "tariffs", "wall street", "stock market", "imf", "dollar", "gdp"],
    "WORLD_TECH_AI": ["artificial intelligence", "nasa", "spacex", "satellite", "semiconductor", "chip", "quantum", "cyber", "robotics", "tech"],
    "CLIMATE_CRISIS": ["climate", "summit", "green energy", "cop", "wildfire", "hurricane", "renewable", "earthquake", "environment"]
}

ENTITY_MAP_INTL = [
    (["binance", "crypto", "hack", "bitcoin", "blockchain"], "digital cryptocurrency blockchain server data center security tech"),
    (["jet", "crash", "aviation", "airplane", "flight"], "emergency rescue services fire response aviation transport incident"),
    (["police", "investigation", "emergency", "crime"], "police vehicle emergency blue lights investigation scene international"),
    (["gaza", "israel", "strike", "middle east", "lebanon"], "Middle East building damage smoke emergency rescue operation"),
    (["protest", "protests", "demonstration", "crowd"], "protesters in European city streets banners demonstration police crowd"),
    (["court", "judge", "lawsuit", "legal"], "Federal court building justice legal courtroom exterior"),
    (["white house", "president", "biden", "trump", "washington"], "White House Washington DC press briefing President United States"),
    (["united nations", "un security council", "diplomacy"], "United Nations Security Council chamber Geneva New York diplomacy"),
    (["nato", "pentagon", "defense secretary", "allies"], "NATO headquarters summit Brussels defense ministers alliance meeting"),
    (["aircraft carrier", "navy", "warship", "fighter jet"], "Modern aircraft carrier warship operations at sea military fighter jet launch"),
    (["space", "nasa", "spacex", "rocket", "satellite"], "NASA rocket launch Cape Canaveral space exploration satellite deployment"),
    (["kremlin", "russia", "putin", "moscow", "ukraine"], "Kremlin Red Square Moscow official government architecture"),
    (["china", "beijing", "xi jinping", "taiwan"], "Great Hall of the People Beijing China official international diplomacy")
]

def map_headline_to_search_query(headline):
    hl = headline.lower()
    for kw_list, query in ENTITY_MAP_INTL:
        if any(k in hl for k in kw_list): return query
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", headline)
    words = [w for w in clean.split() if len(w) > 3 and w.lower() not in {"this", "that", "with", "from", "after", "says", "over", "into"}]
    return " ".join(words[:5]) + " press photo news"

def get_current_edition():
    h = datetime.now(timezone.utc).hour
    if 4 <= h < 12: return "MORNING GLOBAL EDITION", "EUROPE & ASIA BRIEFING"
    elif 12 <= h < 19: return "AFTERNOON GLOBAL WRAP", "EUROPE MIDDAY & US EARLY MARKETS"
    return "PRIME TIME WORLD BROADCAST", "THE AMERICAS & ASIA-PACIFIC LEAD"

# ================= 2. TYPOGRAPHY & TEXT ENGINE =================
def _get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def wrap_text_to_width(text, font, max_width, max_lines=4):
    words = text.split()
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

def classify_headline_topic(headline):
    hl = headline.lower()
    for topic, kws in GLOBAL_TOPICS.items():
        if any(k in hl for k in kws): return topic
    return "GEOPOLITICS"

def load_topic_analytics():
    if os.path.exists(TOPIC_ANALYTICS_FILE):
        try:
            with open(TOPIC_ANALYTICS_FILE, "r") as f: return json.load(f)
        except Exception: pass
    return {k: {"views": 1000, "videos": 1} for k in GLOBAL_TOPICS}

def save_topic_analytics(stats):
    os.makedirs(os.path.dirname(os.path.abspath(TOPIC_ANALYTICS_FILE)), exist_ok=True)
    with open(TOPIC_ANALYTICS_FILE, "w") as f: json.dump(stats, f, indent=2)

def get_recommended_topic():
    stats = load_topic_analytics()
    weights = [max(1, stats.get(t, {}).get("views", 1000)) for t in GLOBAL_TOPICS]
    return random.choices(list(GLOBAL_TOPICS.keys()), weights=weights, k=1)[0]

# ================= 3. GROUND PHOTO & IMAGE ENGINE =================
def _validate_image(data):
    if not data or len(data) < 2000: raise ValueError("Data too small")
    img = Image.open(BytesIO(data)).convert("RGB")
    w, h = img.size
    if w < 40 or h < 40: raise ValueError(f"Dim too small {w}x{h}")
    # Broadcast Color Grading
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.06)
    img = ImageEnhance.Sharpness(img).enhance(1.08)
    return img

def _fetch_article_og_image(url):
    if not url: return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            m = re.search(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', resp.text, re.IGNORECASE)
            if not m: m = re.search(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', resp.text, re.IGNORECASE)
            if m:
                img_url = m.group(1).replace("&amp;", "&")
                r2 = requests.get(img_url, headers=HEADERS, timeout=6)
                if r2.status_code == 200: return _validate_image(r2.content)
    except Exception: pass
    return None

def _fetch_ground_news_photo(query):
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"file:{query}", "gsrlimit": 4, "prop": "imageinfo", "iiprop": "url|size|mime"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                for ii in pdata.get("imageinfo", []):
                    u = ii.get("url", "")
                    if u.lower().endswith((".jpg", ".jpeg", ".png")) and ii.get("width", 0) >= 300:
                        r2 = requests.get(u, headers=HEADERS, timeout=6)
                        if r2.status_code == 200: return _validate_image(r2.content)
    except Exception: pass
    return None

def _fetch_pollinations_image(prompt, w=1280, h=720):
    try:
        safe_prompt = urllib.parse.quote(f"editorial press photography, Reuters photojournalism, authentic news scene: {prompt}, high detail, 8k")
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={w}&height={h}&nologo=true&model=turbo"
        r = requests.get(url, timeout=7)
        if r.status_code == 200: return _validate_image(r.content)
    except Exception: pass
    return None

def create_broadcast_story_card(headline, category, base_img=None, target_w=1280, target_h=720):
    card = Image.new("RGB", (target_w, target_h), (12, 18, 36))
    if base_img:
        bw, bh = base_img.size
        scale = max(target_w / bw, target_h / bh)
        nw, nh = int(bw * scale), int(bh * scale)
        res = base_img.resize((nw, nh), Image.Resampling.LANCZOS)
        cx, cy = (nw - target_w) // 2, (nh - target_h) // 2
        card.paste(res.crop((cx, cy, cx + target_w, cy + target_h)), (0, 0))

    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    # Vignette and bottom news title gradient
    for y in range(target_h):
        if y > int(target_h * 0.45):
            alpha = int(240 * ((y - int(target_h * 0.45)) / (target_h * 0.55)))
            odraw.line([(0, y), (target_w, y)], fill=(8, 12, 28, alpha))
    card.paste(overlay, (0, 0), overlay)

    draw = ImageDraw.Draw(card)
    # Top Category Badge
    badge_w, badge_h = 240, 44
    draw.rectangle([36, 36, 36 + badge_w, 36 + badge_h], fill=(185, 14, 28))
    draw.rectangle([36 + badge_w, 36, 36 + badge_w + 6, 36 + badge_h], fill=(255, 215, 0))
    draw.text((50, 46), f"● {category.upper()}", font=_get_font(22, bold=True), fill=(255, 255, 255))

    # Headline typography
    f_size = 38 if target_w >= 1000 else 28
    font_hl = _get_font(f_size, bold=True)
    wrapped = wrap_text_to_width(headline, font_hl, target_w - 90, max_lines=3)
    y_text = target_h - (len(wrapped) * (f_size + 10)) - 50
    for line in wrapped:
        draw.text((46, y_text + 2), line, font=font_hl, fill=(0, 0, 0))
        draw.text((44, y_text), line, font=font_hl, fill=(255, 255, 255))
        y_text += f_size + 10
    return card

def download_scene_image(scene_info, output_path, target_w=1280, target_h=720):
    img = None
    u = scene_info.get("image_url", "")
    if u and u.startswith("http"):
        try:
            r = requests.get(u, headers=HEADERS, timeout=6)
            if r.status_code == 200: img = _validate_image(r.content)
        except Exception: pass

    if not img and scene_info.get("article_url"):
        img = _fetch_article_og_image(scene_info["article_url"])

    if not img:
        q = map_headline_to_search_query(scene_info["headline"])
        img = _fetch_ground_news_photo(q)

    if not img:
        img = _fetch_pollinations_image(scene_info["headline"], w=target_w, h=target_h)

    if not img and os.path.exists(STUDIO_BG_PATH):
        try: img = Image.open(STUDIO_BG_PATH).convert("RGB")
        except Exception: pass

    card = create_broadcast_story_card(scene_info["headline"], scene_info.get("category", "WORLD"), base_img=img, target_w=target_w, target_h=target_h)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    card.save(output_path, quality=95)
    return output_path

# ================= 4. REAL STUDIO ANCHOR VIDEO ENGINE =================
class RealStudioAnchor:
    def __init__(self, video_path, target_w, target_h):
        self.target_w, self.target_h = target_w, target_h
        self.frames = []
        if os.path.exists(video_path):
            try:
                cmd = ["ffmpeg", "-i", video_path, "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                w, h = 1344, 768
                while True:
                    raw = p.stdout.read(w * h * 3)
                    if not raw or len(raw) < w * h * 3: break
                    im = Image.frombytes("RGB", (w, h), raw)
                    # Crop and fit anchor to target box
                    scale = max(target_w / w, target_h / h)
                    nw, nh = int(w * scale), int(h * scale)
                    res = im.resize((nw, nh), Image.Resampling.LANCZOS)
                    cx, cy = (nw - target_w) // 2, (nh - target_h) // 2
                    self.frames.append(res.crop((cx, cy, cx + target_w, cy + target_h)))
                p.wait()
            except Exception as e:
                logger.warning(f"Failed to load anchor video: {e}")
        # 100% Forward-facing eye-contact loop (frames 5 to 50 + reversed ping-pong)
        if len(self.frames) >= 50:
            fwd = self.frames[5:50]
            self.active_loop = fwd + fwd[::-1]
        elif self.frames:
            self.active_loop = self.frames + self.frames[::-1]
        else:
            self.active_loop = [Image.new("RGB", (target_w, target_h), (12, 18, 36))]

    def get_frame(self, idx):
        return self.active_loop[idx % len(self.active_loop)]

def find_real_anchor_video(gender="female"):
    candidates = [
        f"anchor_real_{gender.lower()}.mp4",
        "anchor_real_male.mp4" if gender.lower() == "male" else "anchor_real_female.mp4",
        "anchor_real.mp4", "anchor_studio.mp4"
    ]
    for c in candidates:
        if os.path.exists(c): return c
    return None

# ================= 5. LIVE GLOBAL RSS & STORY CURATION =================
def _extract_rss_image(entry):
    for th in entry.findall(".//{http://search.yahoo.com/mrss/}thumbnail") + entry.findall(".//media:thumbnail", {"media": "http://search.yahoo.com/mrss/"}):
        u = th.attrib.get("url", "")
        if u:
            # Upgrade BBC 240p thumbnails to 1024p HD
            if "bbci.co.uk" in u or "bbc.com" in u:
                u = re.sub(r'/news/\d+/', '/news/1024/', u)
            return u
    for enc in entry.findall("enclosure"):
        if "image" in enc.attrib.get("type", "").lower() and enc.attrib.get("url"):
            return enc.attrib["url"]
    return ""

def _clean_summary(raw):
    t = re.sub(r"<[^>]+>", "", raw or "").strip()
    t = re.sub(r"\s+", " ", t)
    # Strip only wire source attribution at the end
    t = re.sub(r"\s*-\s*(BBC News|Reuters|The Guardian|AP|Associated Press|Al Jazeera|CNN)$", "", t, flags=re.IGNORECASE)
    return t

def fetch_trending_international_news(category="WORLD", max_stories=5):
    feeds = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml"
    ]
    stories = []
    seen = set()
    for fu in feeds:
        try:
            r = requests.get(fu, headers=HEADERS, timeout=6)
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                title = re.sub(r"\s*-\s*(BBC News|Reuters|The Guardian|AP News|CNN)$", "", title, flags=re.IGNORECASE).strip()
                if not title or title in seen: continue
                seen.add(title)
                link = item.findtext("link", "").strip()
                desc = _clean_summary(item.findtext("description", ""))
                img_url = _extract_rss_image(item)
                cat = classify_headline_topic(f"{title} {desc}")
                stories.append({"headline": title, "summary": desc or title, "article_url": link, "image_url": img_url, "category": cat})
                if len(stories) >= max_stories * 2: break
        except Exception: pass
    random.shuffle(stories)
    return stories[:max_stories]

# ================= 6. SPOKEN SCRIPTWRITER & NEURAL VOICE =================
def humanize_english_anchor_speech(headline, summary, index, total, edition):
    hooks = [
        "In our lead international story tonight,",
        "Turning now to global diplomacy,",
        "In major defense developments,",
        "And in economic updates across key markets,",
        "Finally, in global technology tonight,"
    ]
    hook = hooks[index % len(hooks)]
    clean_s = summary if len(summary.split()) >= 10 else f"{headline}. International authorities are monitoring the developments closely."
    return f"{hook} {headline}. {clean_s}"

def polish_english_bulletin_with_gemini(stories, edition_title, anchor_gender="female"):
    if not GEMINI_API_KEY: return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""You are the senior executive teleprompter scriptwriter for '{CHANNEL_NAME}', a premier international TV news network like BBC World News.
Transform these headlines into natural, articulate, broadcast-ready copy spoken by a top anchor.
Requirements:
1. Short, punchy sentences (12-16 words per breath). Active voice. No robotic or AI clichés.
2. Natural television transition phrases connecting stories.
Return valid JSON with format: {{"bulletin": [{{"headline": "...", "spoken_copy": "..."}}]}}

Stories:
""" + "\n".join([f"{i+1}. {s['headline']} - {s['summary']}" for i, s in enumerate(stories)])
        res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = res.text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m: return json.loads(m.group(0)).get("bulletin")
    except Exception as e:
        logger.warning(f"Gemini script polish fallback: {e}")
    return None

def synthesize_broadcast_voice(text, output_path, gender="female"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    # High-clarity neural broadcast voices
    voice = "en-GB-SoniaNeural" if gender.lower() == "female" else "en-GB-RyanNeural"
    cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", output_path]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
        from gtts import gTTS
        gTTS(text=text, lang="en", tld="co.uk", slow=False).save(output_path)
    return output_path

def create_silence_wav(duration=0.5, output_path="temp/silence.wav"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(duration), output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def _get_audio_duration(path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        out = subprocess.check_output(cmd).decode().strip()
        return float(out)
    except Exception: return 6.0

def generate_pro_broadcast_bed(duration, output_path="temp/broadcast_bed.wav"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    # 120-BPM subtle rhythmic television news pulse (sub-bass kick, tick, and warm pad)
    filter_expr = (
        f"aevalsrc=sin(2*PI*58*t)*exp(-3*mod(t\\,0.5))"
        f"+0.08*sin(2*PI*1200*t)*exp(-30*mod(t\\,0.5))"
        f"+0.04*sin(2*PI*220*t):s=24000:d={duration}"
    )
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", filter_expr, output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

# ================= 7. VIDEO RENDERER (16:9 & 9:16) =================
def build_news_video(script_data, scene_assets, output_path, is_short=True):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    W, H = (1080, 1920) if is_short else (1920, 1080)
    fps = 20

    anchor_vid = find_real_anchor_video(script_data.get("anchor_gender", "female"))
    anchor_engine = RealStudioAnchor(anchor_vid, target_w=(1080 if is_short else 760), target_h=(842 if is_short else 928)) if anchor_vid else None

    silence_pause = create_silence_wav(0.5, "temp/pause.wav")
    silence_outro = create_silence_wav(1.2, "temp/outro.wav")
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

    # Mastered Broadcast Audio Filter Chain (-13 LUFS Loudness, +1.5dB Treble, Ducking Weights)
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", merged_voice, "-i", bgm_path,
        "-filter_complex", "[1:a]highpass=f=75,treble=g=1.5:f=4500,loudnorm=I=-13:LRA=7:TP=-1.0[voice];[2:a]volume=0.07[bgm];[voice][bgm]amix=inputs=2:weights=1.0 0.12:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", output_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    global_frame = 0
    ticker_text = f"  ★★★  {CHANNEL_NAME} WORLDWIDE LIVE  ★★★  {TAGLINE}  ★★★  " + "  |  ".join([sc["headline"] for sc in scene_assets]) + "  ★★★  "

    for sc_idx, sc in enumerate(scene_assets):
        dur = sc.get("duration", 6.0) + (1.2 if sc_idx == len(scene_assets) - 1 else 0.5)
        n_frames = max(1, int(dur * fps))
        story_card = Image.open(sc["image_path"]).convert("RGB")

        for f_idx in range(n_frames):
            frame_img = Image.new("RGB", (W, H), (10, 16, 36))
            anc_frame = anchor_engine.get_frame(global_frame) if anchor_engine else None

            if is_short:
                # 9:16 Shorts Split-Screen Layout (zero black gaps)
                frame_img.paste(story_card.resize((W, 830), Image.Resampling.LANCZOS), (0, 104))
                if anc_frame: frame_img.paste(anc_frame, (0, 998))
                # Top Header
                top_bar = Image.new("RGB", (W, 104), (185, 14, 28))
                tb_draw = ImageDraw.Draw(top_bar)
                tb_draw.ellipse([24, 38, 44, 58], fill=(255, 255, 255))
                tb_draw.text((54, 34), f"{CHANNEL_NAME}  |  GLOBAL LIVE", font=_get_font(28, bold=True), fill=(255, 255, 255))
                tb_draw.text((W - 170, 36), datetime.now(timezone.utc).strftime("%H:%M UTC"), font=_get_font(26, bold=True), fill=(255, 215, 0))
                frame_img.paste(top_bar, (0, 0))
                # Accent Divider
                div_bar = Image.new("RGB", (W, 64), (12, 22, 54))
                dd = ImageDraw.Draw(div_bar)
                dd.line([(0, 0), (W, 0)], fill=(255, 215, 0), width=3)
                dd.text((36, 18), f"● {sc.get('category', 'WORLD')} SPECIAL REPORT", font=_get_font(22, bold=True), fill=(255, 215, 0))
                frame_img.paste(div_bar, (0, 934))
                # Bottom Ticker
                tick = Image.new("RGB", (W, 80), (8, 12, 24))
                td = ImageDraw.Draw(tick)
                td.line([(0, 0), (W, 0)], fill=(185, 14, 28), width=3)
                td.rectangle([0, 0, 140, 80], fill=(185, 14, 28))
                td.text((16, 26), "LATEST", font=_get_font(22, bold=True), fill=(255, 255, 255))
                shift = (global_frame * 5) % (len(ticker_text) * 14 + 800)
                td.text((160 - shift, 26), ticker_text, font=_get_font(22, bold=True), fill=(240, 240, 240))
                frame_img.paste(tick, (0, H - 80))
            else:
                # 16:9 Long Studio Layout (Edge-to-Edge, zero black gaps)
                if anc_frame: frame_img.paste(anc_frame, (0, 76))
                frame_img.paste(story_card.resize((1160, 928), Image.Resampling.LANCZOS), (760, 76))
                # 3D Red-Gold Studio Divider Line at x=760
                dline = ImageDraw.Draw(frame_img)
                dline.line([(760, 76), (760, 1004)], fill=(185, 14, 28), width=4)
                dline.line([(764, 76), (764, 1004)], fill=(255, 215, 0), width=2)
                # Full Header Bar (1920x76)
                hdr = Image.new("RGB", (W, 76), (12, 22, 54))
                hd = ImageDraw.Draw(hdr)
                hd.ellipse([26, 28, 46, 48], fill=(235, 20, 36))
                hd.text((56, 24), f"{CHANNEL_NAME} WORLDWIDE", font=_get_font(26, bold=True), fill=(255, 255, 255))
                hd.text((420, 26), "GLOBAL COVERAGE | INDEPENDENT | VERIFIED", font=_get_font(20), fill=(200, 215, 240))
                hd.text((W - 180, 24), datetime.now(timezone.utc).strftime("%H:%M UTC"), font=_get_font(24, bold=True), fill=(255, 215, 0))
                frame_img.paste(hdr, (0, 0))
                # Full Bottom Ticker (1920x76)
                tick = Image.new("RGB", (W, 76), (8, 12, 24))
                td = ImageDraw.Draw(tick)
                td.line([(0, 0), (W, 0)], fill=(185, 14, 28), width=3)
                td.rectangle([0, 0, 180, 76], fill=(185, 14, 28))
                td.text((24, 24), "BREAKING", font=_get_font(24, bold=True), fill=(255, 255, 255))
                shift = (global_frame * 6) % (len(ticker_text) * 16 + 1200)
                td.text((200 - shift, 24), ticker_text, font=_get_font(24, bold=True), fill=(245, 245, 245))
                frame_img.paste(tick, (0, H - 76))

            proc.stdin.write(frame_img.tobytes())
            global_frame += 1

    proc.stdin.close()
    proc.wait()
    logger.info(f"Broadcast video rendered successfully: {output_path}")
    return output_path

# ================= 8. THUMBNAIL & YOUTUBE ENGINE =================
def generate_broadcast_thumbnail(headline, category, base_img_path, output_path):
    card = Image.open(base_img_path).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(card)
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(720):
        if y > 300: odraw.line([(0, y), (1280, y)], fill=(8, 12, 28, int(230 * ((y - 300) / 420))))
    card.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(card)
    draw.rectangle([40, 40, 320, 96], fill=(185, 14, 28))
    draw.text((54, 52), f"● {CHANNEL_NAME}", font=_get_font(28, bold=True), fill=(255, 255, 255))
    font_th = _get_font(48, bold=True)
    wrapped = wrap_text_to_width(headline.upper(), font_th, 1180, max_lines=2)
    y_pos = 480
    for line in wrapped:
        draw.text((44, y_pos + 3), line, font=font_th, fill=(0, 0, 0))
        draw.text((40, y_pos), line, font=font_th, fill=(255, 215, 0))
        y_pos += 60
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    card.save(output_path, quality=95)
    return output_path

def _get_youtube_token():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN): return None
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SECRET,
            "refresh_token": YT_REFRESH_TOKEN, "grant_type": "refresh_token"
        }, timeout=10)
        if r.status_code == 200: return r.json().get("access_token")
    except Exception as e: logger.warning(f"YouTube OAuth refresh error: {e}")
    return None

def upload_to_youtube(video_path, title, description, tags, thumbnail_path=None, is_short=False):
    token = _get_youtube_token()
    if not token:
        logger.info("YouTube credentials not set; saved locally.")
        return None
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        meta = {
            "snippet": {
                "title": f"{title} #Shorts" if is_short and "#Shorts" not in title else title,
                "description": description,
                "tags": tags[:15],
                "categoryId": "25"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        res = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", headers=headers, json=meta)
        upload_url = res.headers.get("Location")
        with open(video_path, "rb") as f:
            v_res = requests.put(upload_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"}, data=f)
        vid_id = v_res.json().get("id")
        if vid_id and thumbnail_path and os.path.exists(thumbnail_path):
            with open(thumbnail_path, "rb") as tf:
                requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}", headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}, data=tf)
        logger.info(f"Successfully uploaded to YouTube: https://youtu.be/{vid_id}")
        return vid_id
    except Exception as e: logger.error(f"YouTube upload error: {e}")
    return None

# ================= 9. EPISODE ORCHESTRATOR & CLI =================
def produce_news_episode(video_type="both", category="WORLD", edition="auto", anchor_gender="female", skip_upload=False):
    ed_title, ed_sub = get_current_edition()
    logger.info(f"Starting {CHANNEL_NAME} Broadcast: {ed_title} [{category}]")
    stories = fetch_trending_international_news(category=category, max_stories=5)
    if not stories:
        logger.error("No stories retrieved.")
        return

    polished = polish_english_bulletin_with_gemini(stories, ed_title, anchor_gender)
    scene_assets = []
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    for idx, st in enumerate(stories):
        spoken = polished[idx]["spoken_copy"] if (polished and idx < len(polished)) else humanize_english_anchor_speech(st["headline"], st["summary"], idx, len(stories), ed_title)
        card_path = f"temp/card_{idx}.jpg"
        download_scene_image(st, card_path, target_w=1280, target_h=720)
        aud_path = f"temp/voice_{idx}.mp3"
        synthesize_broadcast_voice(spoken, aud_path, gender=anchor_gender)
        dur = _get_audio_duration(aud_path)
        scene_assets.append({"headline": st["headline"], "category": st["category"], "image_path": card_path, "audio_path": aud_path, "duration": dur})

    script_data = {"anchor_gender": anchor_gender}
    lead_headline = stories[0]["headline"]

    if video_type in ("both", "short"):
        short_out = "output/NEXORA_NEWS_SHORT.mp4"
        build_news_video(script_data, scene_assets[:2], short_out, is_short=True)
        if not skip_upload:
            upload_to_youtube(short_out, f"{lead_headline} | {CHANNEL_NAME} LIVE", f"24/7 Global Live Coverage.\n\n#News #BreakingNews #WorldNews #Shorts", ["News", "BreakingNews"], is_short=True)

    if video_type in ("both", "long"):
        long_out = "output/NEXORA_NEWS_BROADCAST.mp4"
        build_news_video(script_data, scene_assets, long_out, is_short=False)
        thumb_out = "output/thumbnail.jpg"
        generate_broadcast_thumbnail(lead_headline, stories[0]["category"], scene_assets[0]["image_path"], thumb_out)
        if not skip_upload:
            desc = f"{CHANNEL_NAME} - {ed_title}\n{TAGLINE}\n\nTop Stories:\n" + "\n".join([f"• {s['headline']}" for s in stories])
            upload_to_youtube(long_out, f"{lead_headline} - {ed_title} | {CHANNEL_NAME}", desc, ["News", "WorldNews", "Global"], thumbnail_path=thumb_out, is_short=False)

    logger.info("Broadcast generation and production complete.")

def main():
    p = argparse.ArgumentParser(description="Nexora News Production Engine")
    p.add_argument("--once", action="store_true", help="Run single broadcast cycle")
    p.add_argument("--type", choices=["both", "short", "long"], default="both")
    p.add_argument("--category", default="WORLD")
    p.add_argument("--edition", default="auto")
    p.add_argument("--anchor", choices=["male", "female", "auto"], default="female")
    p.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    args = p.parse_args()

    produce_news_episode(video_type=args.type, category=args.category, edition=args.edition, anchor_gender=args.anchor, skip_upload=args.skip_upload)

if __name__ == "__main__":
    main()
