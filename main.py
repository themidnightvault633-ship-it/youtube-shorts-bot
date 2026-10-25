import os
import sys
import re
import glob
import html
import json
import time
import math
import random
import asyncio
import logging
import argparse
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("NewsBot")

# ================= 1. CREDENTIALS & CONFIG (ZERO IMPORTERROR) =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "").strip()
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "").strip()
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "").strip()

CATEGORIES = ["NATION", "WORLD", "TECHNOLOGY"]
SHORTS_INTERVAL_HOURS = 3
ENABLE_LONG_VIDEOS = True

NEWS_FEEDS = {
    "NATION": [
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://www.indiatoday.in/rss/1206514",
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "WORLD": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.feedburner.com/ndtvnews-world-news",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "TECHNOLOGY": [
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://feeds.feedburner.com/gadgets360-latest",
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    ],
}

VOICE_MAP = {
    "NATION": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
    "TECHNOLOGY": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
    "WORLD": {"female": "en-US-JennyNeural", "male": "en-US-GuyNeural"},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_ANCHOR_TOGGLE = 0


def _pick_anchor_gender(override=None):
    global _ANCHOR_TOGGLE
    if override in ("male", "female"):
        return override
    gender = "female" if (_ANCHOR_TOGGLE % 2 == 0) else "male"
    _ANCHOR_TOGGLE += 1
    return gender


# ================= 2. BILINGUAL HINDI + ENGLISH FONT ENGINE =================
def _load_font_pair(size=36):
    deva_candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    latin_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    deva_font = None
    for p in deva_candidates:
        if os.path.exists(p):
            try:
                deva_font = ImageFont.truetype(p, size)
                break
            except Exception:
                pass
    latin_font = None
    for p in latin_candidates:
        if os.path.exists(p):
            try:
                latin_font = ImageFont.truetype(p, size)
                break
            except Exception:
                pass
    fallback = latin_font or deva_font or ImageFont.load_default()
    return (deva_font or fallback), (latin_font or fallback)


def draw_bilingual_text(draw, xy, text, size=34, fill=(255, 255, 255)):
    """Routes Devanagari Hindi words to NotoSansDevanagari and English/ASCII to DejaVuSans."""
    deva_font, latin_font = _load_font_pair(size)
    clean = re.sub(r"[\U00010000-\U0010ffff]", "", str(text or ""))
    runs = re.findall(r"[\u0900-\u097F]+|[^\u0900-\u097F]+", clean)
    x, y = xy
    for run in runs:
        is_deva = bool(re.search(r"[\u0900-\u097F]", run))
        font = deva_font if is_deva else latin_font
        draw.text((x, y), run, fill=fill, font=font)
        bbox = draw.textbbox((x, y), run, font=font)
        x += max(0, bbox[2] - bbox[0])
    return x


# ================= 3. LIVE RSS & GEMINI SCRIPT ENGINE =================
def _clean_html_text(raw_text):
    if not raw_text:
        return ""
    text = html.unescape(str(raw_text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_rss_image(item):
    for elem in item.iter():
        tag_lower = elem.tag.lower()
        if tag_lower.endswith(("content", "thumbnail", "enclosure")):
            url = elem.attrib.get("url") or elem.attrib.get("href")
            if url and url.startswith("http") and not url.endswith(".mp3"):
                return url
    for child in item:
        raw = child.text or ""
        m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', raw, re.IGNORECASE)
        if m:
            url = m.group(1)
            if "1x1" not in url and "pixel" not in url:
                return url
    return ""


def fetch_trending_news(category="NATION", max_items=8):
    urls = NEWS_FEEDS.get(category, NEWS_FEEDS["NATION"])
    headlines = []
    seen_titles = set()

    for url in urls:
        if len(headlines) >= max_items:
            break
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = _clean_html_text(item.findtext("title", ""))
                desc = _clean_html_text(item.findtext("description", ""))
                source_el = item.find("source")
                source = _clean_html_text(source_el.text) if source_el is not None and source_el.text else "News Desk"
                media_url = _extract_rss_image(item)

                clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
                norm_key = clean_title[:45].lower()
                if not clean_title or norm_key in seen_titles:
                    continue
                seen_titles.add(norm_key)

                headlines.append({
                    "title": clean_title,
                    "summary": desc[:300] if desc else clean_title,
                    "source": source,
                    "media_url": media_url,
                })
                if len(headlines) >= max_items:
                    break
        except Exception as e:
            logger.warning(f"RSS fetch warning ({url}): {e}")

    return headlines


def _call_gemini_rest(model_name, prompt, api_key, timeout_sec=35):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.65,
            "responseMimeType": "application/json",
        },
    }
    resp = requests.post(url, json=payload, timeout=(10, timeout_sec))
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _build_local_fallback_script(category, headlines, is_short, is_breaking, anchor_gender, language):
    top = headlines[0] if headlines else {
        "title": "भारत और दुनिया की इस वक्त की बड़ी खबरें",
        "summary": "राष्ट्रीय और अंतरराष्ट्रीय स्तर पर आज कई अहम घटनाक्रम सामने आए हैं।",
        "source": "News Bureau",
        "media_url": "",
    }
    top_title = top["title"]
    media_urls = [h.get("media_url", "") for h in headlines if h.get("media_url")]

    if language == "hindi":
        intro = f"नमस्कार, चौबीस घंटे लाइव न्यूज़ बुलेटिन में आपका स्वागत है। इस वक्त की सबसे बड़ी खबर: {top_title}।"
        mid_1 = f"ताज़ा जानकारी के मुताबिक, {headlines[1]['title'] if len(headlines) > 1 else top.get('summary', top_title)}। प्रशासन और विशेषज्ञों की इस पूरे मामले पर कड़ी नज़र बनी हुई है।"
        mid_2 = f"वहीं अगली बड़ी खबर में, {headlines[2]['title'] if len(headlines) > 2 else 'देशभर में इस मुद्दे को लेकर हलचल तेज़ हो गई है और लगातार नए अपडेट सामने आ रहे हैं'}।"
        mid_3 = f"इसके साथ ही एक और महत्वपूर्ण अपडेट सामने आया है: {headlines[3]['title'] if len(headlines) > 3 else 'आर्थिक और तकनीकी मोर्चे पर भी आज कई बड़े फैसले लिए गए हैं'}।"
        mid_4 = f"विशेषज्ञों का मानना है कि {headlines[4]['title'] if len(headlines) > 4 else 'आने वाले कुछ घंटों में इस पूरे मामले पर बड़ा आधिकारिक ऐलान हो सकता है'}।"
        outro = "इन तमाम बड़ी खबरों पर हमारी नज़र लगातार बनी हुई है। पल-पल के सटीक लाइव अपडेट्स के लिए चैनल को अभी सब्सक्राइब करें। नमस्कार।"
        narrations = [intro, mid_1, mid_2, outro] if is_short else [intro, mid_1, mid_2, mid_3, mid_4, outro]
        banner = "बड़ी ख़बर: लाइव अपडेट"
    else:
        intro = f"Welcome to our 24/7 Live Global News broadcast. Our top breaking story this hour: {top_title}."
        mid_1 = f"According to the latest official dispatches, {headlines[1]['title'] if len(headlines) > 1 else top.get('summary', top_title)}. Authorities are closely monitoring the situation."
        mid_2 = f"Meanwhile, in another major development, {headlines[2]['title'] if len(headlines) > 2 else 'new diplomatic and economic responses are unfolding across major global capitals'}."
        mid_3 = f"Furthermore, correspondents report that {headlines[3]['title'] if len(headlines) > 3 else 'key international leaders are convening emergency sessions today'}."
        mid_4 = f"In addition, {headlines[4]['title'] if len(headlines) > 4 else 'global markets and strategic analysts are reacting to these rapid developments'}."
        outro = "We are tracking every development live from our global newsroom. Subscribe now for continuous breaking coverage."
        narrations = [intro, mid_1, mid_2, outro] if is_short else [intro, mid_1, mid_2, mid_3, mid_4, outro]
        banner = "BREAKING NEWS: LIVE REPORT"

    scenes = []
    for idx, text_nar in enumerate(narrations):
        hl = headlines[idx] if idx < len(headlines) else top
        kw = hl.get("title", top_title)
        scenes.append({
            "scene_id": idx + 1,
            "narration": text_nar,
            "subtitles": text_nar,
            "headline_banner": hl.get("title", banner)[:68],
            "search_query": kw,
            "rss_image_url": hl.get("media_url", "") or (media_urls[0] if media_urls else ""),
            "image_prompt": f"Photorealistic editorial news photography of {kw}, BBC and Aaj Tak broadcast journalism style, dramatic lighting, 8k, no text",
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    ticker_items = [h["title"] for h in headlines[:6]] if headlines else [top_title]
    return {
        "category": category,
        "language": language,
        "anchor_gender": anchor_gender,
        "is_breaking": is_breaking,
        "is_short": is_short,
        "title": f"🔴 LIVE: {top_title[:75]} #Shorts" if is_short else f"🔴 LIVE Special Report: {top_title[:72]}",
        "description": f"{top_title}\n\nWatch 24x7 Live News updates in Aaj Tak, News 24 & BBC broadcast style.\n{'#BreakingNews #LiveNews #HindiNews #Shorts' if is_short else '#BreakingNews #LiveNews #HindiNews #SpecialReport'}",
        "tags": ["Breaking News", "Live News", "Hindi News", "Aaj Tak", "News 24", "BBC News", category] + (["Shorts"] if is_short else ["Special Report", "Full Bulletin"]),
        "headline_banner": banner,
        "ticker_text": "  |  ".join(ticker_items),
        "scenes": scenes,
    }


def generate_news_script(category=None, is_short=True, is_breaking=False, anchor_gender=None):
    if not category or category == "AUTO":
        category = random.choice(CATEGORIES)

    cat_upper = category.upper()
    language = "english" if cat_upper == "WORLD" else "hindi"
    chosen_gender = _pick_anchor_gender(anchor_gender)
    headlines = fetch_trending_news(cat_upper, max_items=8)
    num_scenes = 4 if is_short else 6
    words_per_scene = "18 to 26 words" if is_short else "32 to 45 words (in-depth prime-time bulletin analysis)"

    headlines_context = "\n".join(
        [f"{i+1}. Headline: {h['title']} | Details: {h['summary']} (Source: {h['source']})" for i, h in enumerate(headlines)]
    ) or "1. Major National and Global Breaking Developments Today"

    if language == "hindi":
        lang_instruction = (
            "Write ALL `narration`, `subtitles`, `headline_banner`, and `ticker_text` strictly in PURE DEVANAGARI HINDI "
            "(देवनागरी लिपि, e.g., 'नमस्कार, इस वक्त की सबसे बड़ी खबर आ रही है...'). "
            "DO NOT use Romanized Hinglish alphabets so the Hindi neural TTS voice pronounces every word clearly like an Aaj Tak / News 24 anchor."
        )
    else:
        lang_instruction = (
            "Write ALL `narration`, `subtitles`, `headline_banner`, and `ticker_text` in crisp, authoritative "
            "BBC World News broadcast English."
        )

    prompt = f"""You are the Executive Producer for a 24/7 Live Television News Network (BBC News, Aaj Tak, News 24 style).
Create a {num_scenes}-scene {'YouTube Short (9:16)' if is_short else 'Full Prime-Time Special Report Long Video (16:9)'} TV news script from these live headlines:
{headlines_context}

CRITICAL RULES:
1. {lang_instruction}
2. Anchor Gender: "{chosen_gender}".
3. Total scenes: EXACTLY {num_scenes}. Each scene's `narration` must be {words_per_scene}.
4. Return ONLY valid JSON with this exact structure:
{{
  "title": "Catchy YouTube title (max 85 chars, {'include #Shorts' if is_short else 'DO NOT include #Shorts'})",
  "description": "YouTube description with summary and hashtags",
  "tags": ["Breaking News", "Live News"],
  "headline_banner": "Main top story strap (4-7 words)",
  "ticker_text": "4-5 top headlines separated by | for the bottom scrolling news ticker",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "...",
      "subtitles": "...",
      "headline_banner": "...",
      "search_query": "4-6 English keywords for event photo search",
      "image_prompt": "Photorealistic editorial news photography of the event, no text",
      "camera_angle": "wide"
    }}
  ]
}}"""

    if GEMINI_API_KEY:
        for model_name in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                logger.info(f"Requesting {'SHORT' if is_short else 'LONG'} script from {model_name} (lang={language}, anchor={chosen_gender})...")
                raw_json = _call_gemini_rest(model_name, prompt, GEMINI_API_KEY, timeout_sec=35)
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip(), flags=re.MULTILINE)
                data = json.loads(cleaned)
                scenes = data.get("scenes", [])
                if not scenes:
                    raise ValueError("Empty scenes")
                for idx, sc in enumerate(scenes):
                    hl = headlines[idx] if idx < len(headlines) else (headlines[0] if headlines else {})
                    sc["scene_id"] = idx + 1
                    sc["rss_image_url"] = hl.get("media_url", "")
                    if not sc.get("search_query"):
                        sc["search_query"] = hl.get("title", "Breaking News")
                    if not sc.get("headline_banner"):
                        sc["headline_banner"] = data.get("headline_banner", "BREAKING NEWS")
                    if not sc.get("camera_angle"):
                        sc["camera_angle"] = "closeup" if idx % 2 == 1 else "wide"
                data["category"] = cat_upper
                data["language"] = language
                data["anchor_gender"] = chosen_gender
                data["is_breaking"] = is_breaking
                data["is_short"] = is_short
                logger.info(f"✅ Generated {len(scenes)}-scene {language.upper()} script via {model_name}")
                return data
            except Exception as e:
                logger.warning(f"Model {model_name} fallback: {e}")
                time.sleep(1)

    logger.info("Using live-RSS broadcast script builder...")
    return _build_local_fallback_script(cat_upper, headlines, is_short, is_breaking, chosen_gender, language)


# ================= 4. NEURAL VOICE ENGINE =================
async def _edge_tts_save(text, voice, rate, output_path):
    import edge_tts
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="+0Hz")
    await asyncio.wait_for(comm.save(output_path), timeout=25.0)


def synthesize_broadcast_voice(text, output_path, category="NATION", gender="female", language="hindi"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    clean_text = (text or "").strip() or "नमस्कार, ताज़ा खबरों के लिए हमारे साथ जुड़े रहिए।"
    cat_upper = (category or "NATION").upper()
    g_key = "male" if str(gender).lower() == "male" else "female"

    if str(language).lower() == "english" or cat_upper == "WORLD":
        voice = VOICE_MAP["WORLD"][g_key]
        rate = "+6%"
        lang_code = "en"
    else:
        voice = VOICE_MAP["NATION"][g_key]
        rate = "+8%"
        lang_code = "hi"

    for attempt in range(1, 3):
        try:
            logger.info(f"🎙️ Generating Neural Voice ({voice}, gender={g_key}, attempt={attempt})...")
            asyncio.run(_edge_tts_save(clean_text, voice, rate, output_path))
            if os.path.exists(output_path) and os.path.getsize(output_path) > 800:
                return output_path
        except Exception as e:
            logger.warning(f"Edge-TTS attempt {attempt} warning: {e}")

    try:
        from gtts import gTTS
        tts = gTTS(text=clean_text, lang=lang_code, slow=False)
        tts.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return output_path
    except Exception:
        pass

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
            "-t", "6.0", "-af", "volume=0.02", output_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    return output_path


# ================= 5. REAL EVENT PHOTO & ANCHOR IMAGE ENGINE =================
def _validate_and_resize_image(raw_bytes, target_w, target_h):
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size
    if w < 220 or h < 180:
        raise ValueError("Image too small")
    arr = np.asarray(img, dtype=np.float32)
    if arr.std() < 8.0:
        raise ValueError("Blank image")

    target_ratio = target_w / float(target_h)
    src_ratio = w / float(h)
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.10)
    return img


def _fetch_bing_news_image(query, target_w, target_h):
    clean_q = re.sub(r"[^\w\s]", " ", query or "").strip()
    if not clean_q:
        return None
    search_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_q + ' news photo')}&form=HDRSC2&first=1"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text) or re.findall(r'"murl":"(https?://[^"]+?)"', resp.text)
        for img_url in urls[:5]:
            if any(bad in img_url.lower() for bad in [".svg", ".gif", "logo", "icon", "avatar"]):
                continue
            try:
                ir = requests.get(img_url, headers=HEADERS, timeout=8)
                if ir.status_code == 200 and len(ir.content) > 12000:
                    return _validate_and_resize_image(ir.content, target_w, target_h)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fetch_pollinations_image(prompt, target_w, target_h):
    gen_w, gen_h = 1024, 1024
    clean_prompt = re.sub(r"[^\w\s,.-]", " ", prompt or "Editorial news photojournalism").strip()
    encoded = urllib.parse.quote(clean_prompt[:280])
    for model in ["flux", "turbo"]:
        seed = random.randint(1000, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&seed={seed}&model={model}&nologo=true"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 15000:
                return _validate_and_resize_image(resp.content, target_w, target_h)
        except Exception:
            pass
    return None


def _create_broadcast_broll_graphic(output_path, width, height, headline_text=""):
    img = Image.new("RGB", (width, height), (12, 18, 38))
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    for r in range(max(width, height) // 2, 20, -25):
        ratio = 1.0 - (r / float(max(width, height) // 2))
        col = (int(12 + 95 * ratio), int(20 + 25 * ratio), int(42 + 80 * ratio))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    for lat in range(60, height, 65):
        draw.line([(0, lat), (width, lat)], fill=(45, 75, 130), width=1)
    for lon in range(60, width, 65):
        draw.line([(lon, 0), (lon, height)], fill=(45, 75, 130), width=1)

    card_w, card_h = int(width * 0.86), int(height * 0.44)
    x0, y0 = (width - card_w) // 2, (height - card_h) // 2 + 25
    draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=18, fill=(18, 26, 52), outline=(255, 195, 0), width=4)
    draw.rectangle([x0, y0, x0 + card_w, y0 + 56], fill=(195, 18, 30))
    draw.ellipse([x0 + 22, y0 + 18, x0 + 42, y0 + 38], fill=(255, 255, 255))
    draw_bilingual_text(draw, (x0 + 54, y0 + 12), "LIVE SATELLITE NEWS FEED  |  24x7", size=28, fill=(255, 255, 255))

    clean_hl = (headline_text or "LIVE BREAKING NEWS UPDATE").strip()
    words = clean_hl.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= 30:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    ty = y0 + 82
    for line in lines[:3]:
        draw_bilingual_text(draw, (x0 + 28, ty), line, size=36, fill=(255, 245, 215))
        ty += 52

    img.save(output_path, "JPEG", quality=92)
    return output_path


def download_scene_image(prompt, output_path, is_short=True, search_query="", rss_image_url="", headline_text=""):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w = 1080 if is_short else 1280
    target_h = 880 if is_short else 880

    if rss_image_url and rss_image_url.startswith("http"):
        try:
            resp = requests.get(rss_image_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 10000:
                img = _validate_and_resize_image(resp.content, target_w, target_h)
                img.save(output_path, "JPEG", quality=92)
                return output_path
        except Exception:
            pass

    q = search_query or headline_text or prompt
    img = _fetch_bing_news_image(q, target_w, target_h)
    if img is not None:
        logger.info(f"🖼️ Downloaded real event news photo for: {q[:45]}")
        img.save(output_path, "JPEG", quality=92)
        return output_path

    logger.info(f"🎨 Generating AI News B-Roll (1024x1024 -> {target_w}x{target_h})...")
    img = _fetch_pollinations_image(prompt, target_w, target_h)
    if img is not None:
        img.save(output_path, "JPEG", quality=92)
        return output_path

    return _create_broadcast_broll_graphic(output_path, target_w, target_h, headline_text=headline_text or search_query)


def _create_procedural_studio_anchor(output_path, anchor_gender="female", width=1080, height=960):
    img = Image.new("RGB", (width, height), (14, 18, 34))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        r = int(14 + 28 * (y / float(height)))
        g = int(20 + 18 * (y / float(height)))
        b = int(42 + 45 * (y / float(height)))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    for y_bar in [120, 240, 360, 480]:
        draw.rectangle([40, y_bar, width - 40, y_bar + 8], fill=(200, 30, 45))
        draw.rectangle([80, y_bar + 14, width - 80, y_bar + 18], fill=(0, 170, 240))

    cx = width // 2
    suit_color = (22, 28, 48) if anchor_gender == "male" else (155, 22, 38)
    draw.polygon([(cx - 270, height - 120), (cx + 270, height - 120), (cx + 210, 520), (cx - 210, 520)], fill=suit_color)
    draw.polygon([(cx - 55, 520), (cx + 55, 520), (cx, 720)], fill=(242, 245, 250))
    if anchor_gender == "male":
        draw.polygon([(cx - 18, 545), (cx + 18, 545), (cx + 24, 710), (cx - 24, 710)], fill=(195, 20, 32))

    skin = (224, 172, 138)
    draw.rectangle([cx - 42, 430, cx + 42, 545], fill=skin)
    draw.ellipse([cx - 115, 220, cx + 115, 485], fill=skin)

    if anchor_gender == "female":
        draw.pieslice([cx - 128, 195, cx + 128, 460], 160, 380, fill=(24, 18, 16))
        draw.polygon([(cx - 125, 310), (cx - 95, 535), (cx - 65, 520)], fill=(24, 18, 16))
        draw.polygon([(cx + 125, 310), (cx + 95, 535), (cx + 65, 520)], fill=(24, 18, 16))
    else:
        draw.pieslice([cx - 120, 200, cx + 120, 390], 175, 365, fill=(22, 18, 16))

    eye_y = 335
    for ex in [cx - 46, cx + 46]:
        draw.ellipse([ex - 22, eye_y - 10, ex + 22, eye_y + 10], fill=(250, 250, 250))
        draw.ellipse([ex - 9, eye_y - 9, ex + 9, eye_y + 9], fill=(38, 26, 20))
        draw.ellipse([ex - 3, eye_y - 3, ex + 3, eye_y + 3], fill=(255, 255, 255))
        draw.arc([ex - 26, eye_y - 22, ex + 26, eye_y - 4], 190, 350, fill=(28, 20, 18), width=4)

    draw.line([(cx, 340), (cx - 6, 395), (cx + 8, 398)], fill=(185, 132, 102), width=3)
    mouth_y = 428
    lip_col = (185, 55, 68) if anchor_gender == "female" else (165, 78, 74)
    draw.polygon([(cx - 38, mouth_y), (cx, mouth_y - 9), (cx + 38, mouth_y), (cx, mouth_y + 12)], fill=lip_col)
    draw.line([(cx - 34, mouth_y), (cx + 34, mouth_y)], fill=(90, 25, 30), width=2)
    draw.rectangle([0, height - 150, width, height], fill=(16, 22, 44))
    draw.rectangle([0, height - 150, width, height - 138], fill=(225, 180, 0))
    img.save(output_path, "JPEG", quality=94)
    return output_path


def download_anchor_studio_image(anchor_gender="female", category="NATION", output_path="temp/anchor_studio.jpg"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w, target_h = 1080, 960
    gender_word = "handsome Indian male" if str(anchor_gender).lower() == "male" else "graceful Indian female"
    attire = (
        "wearing a sharp dark navy business suit, crisp white shirt, and red silk tie, lapel microphone"
        if str(anchor_gender).lower() == "male"
        else "wearing a professional crimson-red and dark navy news blazer, lapel microphone"
    )
    if str(category).upper() == "WORLD":
        gender_word = "charismatic international male" if str(anchor_gender).lower() == "male" else "charismatic international female"

    prompt = (
        f"Front-facing medium close-up portrait of a {gender_word} television news anchor {attire}, "
        f"sitting dead-center at a sleek modern BBC and Aaj Tak live broadcast studio desk, "
        f"looking directly into the camera lens with a composed authoritative expression, "
        f"head centered vertically in the upper-middle frame, glowing red and blue LED newsroom screens behind, "
        f"8k UHD photorealistic broadcast television lighting, canon C300 lens, no text"
    )
    logger.info(f"🧑‍💼 Fetching photorealistic {anchor_gender.upper()} TV News Anchor for {category}...")
    img = _fetch_pollinations_image(prompt, target_w, target_h)
    if img is not None:
        img.save(output_path, "JPEG", quality=94)
        return output_path
    return _create_procedural_studio_anchor(output_path, anchor_gender=anchor_gender, width=target_w, height=target_h)


# ================= 6. 30FPS AUDIO-REACTIVE ANCHOR & BROADCAST RENDERER =================
def _get_audio_duration(audio_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        return max(2.0, float(out))
    except Exception:
        return 6.5


def _extract_audio_envelope(audio_path, duration, fps=30):
    n_frames = max(1, int(math.ceil(duration * fps)) + 2)
    sample_rate = 1500
    try:
        cmd = ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
        if pcm.size < 10:
            raise ValueError("Empty PCM")
        samples_per_frame = max(1, sample_rate // fps)
        target_len = n_frames * samples_per_frame
        pcm = np.pad(pcm, (0, max(0, target_len - pcm.size)))[:target_len]
        frames_pcm = pcm.reshape((n_frames, samples_per_frame))
        rms = np.sqrt(np.mean(frames_pcm ** 2, axis=1))
        p95 = np.percentile(rms, 95) if rms.size > 0 else 1.0
        env = np.clip(rms / max(p95, 100.0), 0.0, 1.0)
        return np.convolve(env, np.array([0.2, 0.6, 0.2], dtype=np.float32), mode="same")
    except Exception:
        t = np.linspace(0, duration, n_frames)
        return 0.45 + 0.45 * np.abs(np.sin(2.0 * np.pi * 3.8 * t))


def _detect_anchor_landmarks(anchor_rgb):
    h, w, _ = anchor_rgb.shape
    y0, y1 = int(h * 0.14), int(h * 0.62)
    x0, x1 = int(w * 0.28), int(w * 0.72)
    roi = anchor_rgb[y0:y1, x0:x1].astype(np.float32)
    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    skin_mask = (r > 95) & (g > 55) & (b > 35) & ((r - g) > 12) & ((r - b) > 22) & (r < 250)
    if np.count_nonzero(skin_mask) > 400:
        ys, xs = np.where(skin_mask)
        cx = x0 + int(np.median(xs))
        cy_face = y0 + int(np.percentile(ys, 48))
        face_h = max(140, int(np.percentile(ys, 90) - np.percentile(ys, 10)))
        return cx, cy_face - int(face_h * 0.14), cy_face + int(face_h * 0.22), face_h
    return w // 2, int(h * 0.34), int(h * 0.44), int(h * 0.26)


class BroadcastAnchorAnimator:
    def __init__(self, anchor_img_path, width=1080, height=790):
        self.w = width
        self.h = height
        raw = Image.open(anchor_img_path).convert("RGB")
        src_w, src_h = raw.size
        target_ratio = width / float(height)
        src_ratio = src_w / float(src_h)
        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            raw = raw.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            raw = raw.crop((0, top, src_w, top + new_h))

        raw = raw.resize((width, height), Image.Resampling.LANCZOS)
        self.base = np.asarray(raw, dtype=np.uint8)
        self.gw, self.gh = width // 2, height // 2
        self.small_base = np.asarray(raw.resize((self.gw, self.gh), Image.Resampling.BILINEAR), dtype=np.uint8)

        cx, eye_y, mouth_y, face_h = _detect_anchor_landmarks(self.base)
        self.cx, self.eye_y, self.mouth_y = cx // 2, eye_y // 2, mouth_y // 2
        self.face_r = max(36, face_h // 4)

        yy, xx = np.meshgrid(np.arange(self.gh, dtype=np.float32), np.arange(self.gw, dtype=np.float32), indexing="ij")
        self.xx, self.yy = xx, yy
        self.head_mask = np.exp(-(((xx - self.cx) / (self.face_r * 1.45)) ** 2 + ((yy - (self.mouth_y - 12)) / (self.face_r * 1.65)) ** 2))
        self.body_mask = np.exp(-(((xx - self.cx) / (self.face_r * 2.6)) ** 2 + ((yy - (self.mouth_y + 75)) / (self.face_r * 2.2)) ** 2))
        jaw_cy = self.mouth_y + int(self.face_r * 0.24)
        self.jaw_mask = np.exp(-(((xx - self.cx) / (self.face_r * 0.52)) ** 2 + ((yy - jaw_cy) / (self.face_r * 0.38)) ** 2))
        self.lip_aperture = np.exp(-(((xx - self.cx) / (self.face_r * 0.26)) ** 2 + ((yy - self.mouth_y) / (self.face_r * 0.11)) ** 2))[:, :, None]

        eye_sep = int(self.face_r * 0.44)
        left_eye = np.exp(-(((xx - (self.cx - eye_sep)) / 11.0) ** 2 + ((yy - self.eye_y) / 5.5) ** 2))
        right_eye = np.exp(-(((xx - (self.cx + eye_sep)) / 11.0) ** 2 + ((yy - self.eye_y) / 5.5) ** 2))
        self.blink_mask = np.clip(left_eye + right_eye, 0.0, 1.0)

    def render_frame(self, t, speech_amp, camera_angle="wide", broll_thumb=None):
        nod_y = (1.6 * math.sin(t * 2.7) + 2.2 * speech_amp * math.sin(t * 6.5)) * self.head_mask
        sway_x = (1.5 * math.sin(t * 1.4) + 1.0 * speech_amp * math.cos(t * 4.2)) * (self.head_mask + 0.5 * self.body_mask)
        breath_y = 1.2 * math.sin(t * 1.8) * self.body_mask
        jaw_open = (4.8 * (speech_amp ** 1.15) + 0.6 * abs(math.sin(t * 9.0)) * speech_amp) * self.jaw_mask
        blink_strength = math.exp(-(((t % 3.4) - 1.7) / 0.065) ** 2)
        blink_pull = 3.2 * blink_strength * self.blink_mask

        src_x = np.clip(np.rint(self.xx - sway_x).astype(np.int32), 0, self.gw - 1)
        src_y = np.clip(np.rint(self.yy - nod_y - breath_y - jaw_open - blink_pull).astype(np.int32), 0, self.gh - 1)
        warped_small = self.small_base[src_y, src_x].astype(np.float32)
        if speech_amp > 0.18:
            warped_small = warped_small * (1.0 - (0.38 * speech_amp * self.lip_aperture))

        frame_pil = Image.fromarray(np.clip(warped_small, 0, 255).astype(np.uint8)).resize((self.w, self.h), Image.Resampling.BILINEAR)
        if broll_thumb is not None:
            pip_w, pip_h = min(240, self.w // 4), min(140, self.h // 5)
            pip_img = broll_thumb.resize((pip_w, pip_h), Image.Resampling.BILINEAR)
            draw_pip = ImageDraw.Draw(frame_pil)
            px, py = self.w - pip_w - 24, 34
            draw_pip.rectangle([px - 4, py - 4, px + pip_w + 4, py + pip_h + 4], fill=(225, 30, 45), outline=(255, 200, 0), width=2)
            frame_pil.paste(pip_img, (px, py))

        zoom = (1.14 + 0.02 * math.sin(t * 0.5)) if camera_angle == "closeup" else (1.02 + 0.03 * math.sin(t * 0.4))
        cw, ch = int(self.w / zoom), int(self.h / zoom)
        x0, y0 = (self.w - cw) // 2, max(0, int((self.h - ch) * 0.32))
        frame_pil = frame_pil.crop((x0, y0, x0 + cw, y0 + ch)).resize((self.w, self.h), Image.Resampling.BILINEAR)
        return np.asarray(frame_pil, dtype=np.uint8)


def _split_caption_chunks(text, max_words_per_chunk=7):
    words = (text or "").strip().split()
    if not words:
        return [""]
    return [" ".join(words[i : i + max_words_per_chunk]) for i in range(0, len(words), max_words_per_chunk)]


def _create_bgm_wav(total_duration, bgm_path="temp/broadcast_bgm.wav"):
    sr = 22050
    n_samples = int(total_duration * sr)
    t = np.linspace(0, total_duration, n_samples, endpoint=False)
    pad = 0.35 * np.sin(2 * np.pi * 110.0 * t) + 0.25 * np.sin(2 * np.pi * 165.0 * t)
    pulse = (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)) ** 3
    beeps = 0.20 * np.sin(2 * np.pi * 440.0 * t) * pulse
    wave = np.clip((pad + beeps) * 0.045, -0.9, 0.9)
    os.makedirs(os.path.dirname(os.path.abspath(bgm_path)), exist_ok=True)
    pcm16 = (wave * 32767).astype(np.int16)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-", bgm_path],
        input=pcm16.tobytes(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    return bgm_path if os.path.exists(bgm_path) else None


def build_news_video(script_data, scene_assets, output_path, is_short=True, anchor_img_path=None):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    fps = 30
    W, H = (1080, 1920) if is_short else (1920, 1080)

    language = script_data.get("language", "hindi")
    category = script_data.get("category", "NATION").upper()
    ticker_raw = script_data.get("ticker_text") or script_data.get("headline_banner") or "LIVE BREAKING NEWS UPDATES"

    ticker_clean = re.sub(r"•", " | ", ticker_raw)
    ticker_unit = f"   [LIVE 24x7]  {ticker_clean}   |   BREAKING NEWS   |   "
    ticker_full = ticker_unit * 4

    ticker_w = max(W * 4, len(ticker_full) * 18)
    ticker_h = 56
    ticker_strip = Image.new("RGB", (ticker_w, ticker_h), (245, 196, 0))
    t_draw = ImageDraw.Draw(ticker_strip)
    t_draw.rectangle([0, 0, ticker_w, 4], fill=(190, 15, 25))
    end_x = draw_bilingual_text(t_draw, (20, 10), ticker_full, size=30, fill=(10, 12, 18))
    unit_px = max(450, (end_x - 20) // 4)
    ticker_arr = np.asarray(ticker_strip, dtype=np.uint8)

    if is_short:
        broll_win_w, broll_win_h = W, 820
        anchor_w, anchor_h = W, 790
        strap_h, sub_h = 112, 98
        max_words_chunk, hl_max_chars = 7, 44
    else:
        broll_win_w, broll_win_h = 1120, 850
        anchor_w, anchor_h = 800, 850
        strap_h, sub_h = 86, 88
        max_words_chunk, hl_max_chars = 12, 78

    animator = BroadcastAnchorAnimator(anchor_img_path, width=anchor_w, height=anchor_h)
    prepared_scenes = []
    concat_list_path = "temp/audio_concat.txt"
    total_duration = 0.0

    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for idx, asset in enumerate(scene_assets):
            dur = _get_audio_duration(asset["audio_path"])
            env = _extract_audio_envelope(asset["audio_path"], dur, fps=fps)
            f_concat.write(f"file '{os.path.abspath(asset['audio_path'])}'\n")

            broll_pil = Image.open(asset["image_path"]).convert("RGB")
            broll_base = broll_pil.resize((int(broll_win_w * 1.14), int(broll_win_h * 1.14)), Image.Resampling.LANCZOS)
            broll_thumb = broll_pil.resize((240, 140), Image.Resampling.BILINEAR)

            headline_banner = asset.get("headline_banner") or script_data.get("headline_banner", "BREAKING NEWS")
            narration = asset.get("subtitles") or asset.get("narration", "")
            cam_angle = asset.get("camera_angle", "closeup" if idx % 2 == 1 else "wide")
            caption_chunks = _split_caption_chunks(narration, max_words_per_chunk=max_words_chunk)

            strap_img = Image.new("RGBA", (W, strap_h), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(strap_img)
            s_draw.rectangle([0, 0, W, strap_h], fill=(155, 12, 24, 248))
            s_draw.rectangle([0, 0, W, 5], fill=(255, 205, 0, 255))
            s_draw.rectangle([0, strap_h - 5, W, strap_h], fill=(255, 205, 0, 255))
            badge_label = "बड़ी ख़बर" if language == "hindi" else "BREAKING"
            s_draw.polygon([(0, 5), (245, 5), (220, strap_h - 5), (0, strap_h - 5)], fill=(250, 195, 0, 255))
            ty_strap = (strap_h - 34) // 2
            draw_bilingual_text(s_draw, (24, ty_strap), badge_label, size=28, fill=(15, 15, 20, 255))

            hl_clean = headline_banner.strip()
            if len(hl_clean) > hl_max_chars:
                hl_clean = hl_clean[: hl_max_chars - 2] + "..."
            draw_bilingual_text(s_draw, (256, ty_strap - 2), hl_clean, size=34, fill=(255, 255, 255, 255))
            strap_rgb = np.asarray(strap_img.convert("RGB"), dtype=np.uint8)

            sub_cards = []
            for chunk in caption_chunks:
                sc_img = Image.new("RGB", (W, sub_h), (10, 14, 28))
                sc_draw = ImageDraw.Draw(sc_img)
                sc_draw.rectangle([0, 0, W, 4], fill=(0, 195, 255))
                sc_draw.rounded_rectangle([24, 10, W - 24, sub_h - 8], radius=12, fill=(18, 24, 46), outline=(255, 205, 0), width=2)
                cy_dot = sub_h // 2
                sc_draw.ellipse([42, cy_dot - 9, 60, cy_dot + 9], fill=(235, 30, 45))
                speaker_tag = "एंकर:" if language == "hindi" else "ANCHOR:"
                draw_bilingual_text(sc_draw, (72, cy_dot - 19), f"{speaker_tag}  {chunk}", size=32, fill=(255, 248, 210))
                sub_cards.append(np.asarray(sc_img, dtype=np.uint8))

            prepared_scenes.append({
                "idx": idx,
                "dur": dur,
                "start_t": total_duration,
                "env": env,
                "broll_base": broll_base,
                "broll_thumb": broll_thumb,
                "strap_rgb": strap_rgb,
                "sub_cards": sub_cards,
                "cam_angle": cam_angle,
            })
            total_duration += dur

    merged_voice_wav = "temp/merged_voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-ar", "24000", "-ac", "1", merged_voice_wav],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=45,
    )
    bgm_wav = _create_bgm_wav(total_duration, "temp/broadcast_bgm.wav")
    final_audio_wav = "temp/final_mixed_audio.wav"
    if bgm_wav and os.path.exists(merged_voice_wav):
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", merged_voice_wav, "-i", bgm_wav,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[aout]", final_audio_wav,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
    else:
        final_audio_wav = merged_voice_wav

    logger.info(f"🎬 Rendering 30fps {'SHORT (9:16)' if is_short else 'LONG (16:9)'} Video ({total_duration:.1f}s) to {output_path}...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "-", "-i", final_audio_wav,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for sc in prepared_scenes:
        n_frames = max(1, int(round(sc["dur"] * fps)))
        idx, dur, env = sc["idx"], sc["dur"], sc["env"]
        broll_base, broll_thumb = sc["broll_base"], sc["broll_thumb"]
        strap_rgb, sub_cards = sc["strap_rgb"], sc["sub_cards"]
        cam_angle, scene_start_t = sc["cam_angle"], sc["start_t"]

        for f_i in range(n_frames):
            t = f_i / float(fps)
            gt = scene_start_t + t
            speech_amp = float(env[min(len(env) - 1, f_i)])

            prog = min(1.0, max(0.0, t / max(0.1, dur)))
            bw, bh = broll_base.size
            if idx % 2 == 0:
                crop_x = int((bw - broll_win_w) * prog * 0.75)
                crop_y = int((bh - broll_win_h) * (1.0 - prog) * 0.65)
            else:
                crop_x = int((bw - broll_win_w) * (1.0 - prog) * 0.75)
                crop_y = int((bh - broll_win_h) * prog * 0.65)
            top_pil = broll_base.crop((crop_x, crop_y, crop_x + broll_win_w, crop_y + broll_win_h)).copy()

            top_draw = ImageDraw.Draw(top_pil)
            pulse_red = (235, 20, 35) if int(gt * 2.5) % 2 == 0 else (175, 12, 22)
            top_draw.rounded_rectangle([32, 36, 248, 90], radius=10, fill=pulse_red, outline=(255, 255, 255), width=2)
            top_draw.ellipse([50, 53, 70, 73], fill=(255, 255, 255))
            draw_bilingual_text(top_draw, (82, 46), "LIVE 24x7", size=26, fill=(255, 255, 255))
            top_draw.rounded_rectangle([260, 36, 475, 90], radius=10, fill=(14, 22, 48), outline=(255, 200, 0), width=2)
            draw_bilingual_text(top_draw, (282, 46), category, size=26, fill=(255, 215, 0))
            broll_arr = np.asarray(top_pil, dtype=np.uint8)

            anchor_arr = animator.render_frame(gt, speech_amp=speech_amp, camera_angle=cam_angle, broll_thumb=broll_thumb if is_short else None)
            canvas = np.zeros((H, W, 3), dtype=np.uint8)
            chunk_idx = min(len(sub_cards) - 1, int((t / max(0.1, dur)) * len(sub_cards)))
            scroll_x = int(gt * 165) % max(1, min(unit_px, ticker_arr.shape[1] - W - 1))

            if is_short:
                canvas[0:820, :, :] = broll_arr
                canvas[820:932, :, :] = strap_rgb
                canvas[932:1722, :, :] = anchor_arr
                canvas[1445:1543, :, :] = sub_cards[chunk_idx]
                bar_w = int(W * (0.18 + 0.72 * speech_amp))
                x_start = (W - bar_w) // 2
                canvas[1435:1443, x_start : x_start + bar_w, :] = (255, 65, 75)
                canvas[1543:1599, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]
                canvas[1599:1606, :, :] = (220, 25, 35)
            else:
                canvas[0:850, 0:1120, :] = broll_arr
                canvas[0:850, 1120:1920, :] = anchor_arr
                canvas[0:850, 1116:1124, :] = (255, 200, 0)
                canvas[850:936, :, :] = strap_rgb
                canvas[936:1024, :, :] = sub_cards[chunk_idx]
                canvas[1024:1080, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]

            proc.stdin.write(canvas.tobytes())

    proc.stdin.close()
    proc.wait(timeout=180)
    logger.info(f"✅ Broadcast Video Rendered: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
    return output_path


# ================= 7. YOUTUBE UPLOAD & ORCHESTRATOR =================
def cleanup_temp_files():
    os.makedirs("temp", exist_ok=True)
    for f in glob.glob("temp/*"):
        try:
            os.remove(f)
        except Exception:
            pass


def upload_to_youtube(video_path, script_data, is_short=True):
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        logger.warning("⚠️ YouTube OAuth credentials missing! Video saved locally at: " + video_path)
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials(
            None,
            refresh_token=YT_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YT_CLIENT_ID,
            client_secret=YT_CLIENT_SECRET,
        )
        creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds)

        raw_title = script_data.get("title", "🔴 LIVE Breaking News Update")
        if is_short:
            title = f"{raw_title[:88]} #Shorts" if ("#Shorts" not in raw_title and "#shorts" not in raw_title) else raw_title[:100]
        else:
            title = raw_title.replace("#Shorts", "").replace("#shorts", "").strip()[:100]

        description = script_data.get("description", "24x7 Live News Bulletin.")
        if not is_short:
            description = description.replace("#Shorts", "#LongVideo")

        tags = script_data.get("tags", ["Breaking News", "Live News", "Hindi News"])
        if not is_short:
            tags = [t for t in tags if t.lower() not in ("shorts", "#shorts")] + ["Special Report", "Full Bulletin"]

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": tags[:15],
                "categoryId": "25",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 5, resumable=True, mimetype="video/mp4")
        logger.info(f"📤 Uploading {'SHORT' if is_short else 'LONG VIDEO'} to YouTube: {title[:70]}...")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()

        vid_id = response.get("id")
        logger.info(f"✅ Successfully uploaded to YouTube! Video ID: {vid_id} (https://youtu.be/{vid_id})")
        return vid_id
    except Exception as e:
        logger.error(f"❌ YouTube Upload Failed: {e}")
        return None


def produce_news_episode(category="AUTO", is_short=True, is_breaking=False, anchor_gender=None, skip_upload=False):
    logger.info("==========================================")
    logger.info(f"🎬 Starting Production: {category} | Format: {'SHORT (9:16)' if is_short else 'LONG (16:9)'} | Breaking: {is_breaking}")
    logger.info("==========================================")

    cleanup_temp_files()
    os.makedirs("output", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    script_data = generate_news_script(
        category=category,
        is_short=is_short,
        is_breaking=is_breaking,
        anchor_gender=anchor_gender,
    )
    resolved_cat = script_data.get("category", "NATION")
    language = script_data.get("language", "hindi")
    chosen_gender = script_data.get("anchor_gender", "female")
    scenes = script_data.get("scenes", [])

    logger.info(
        f"📋 Script Ready: '{script_data.get('title')}' | Category: {resolved_cat} | "
        f"Language: {language.upper()} | Anchor: {chosen_gender.upper()} | Scenes: {len(scenes)}"
    )

    anchor_img_path = f"temp/anchor_{chosen_gender}_{resolved_cat.lower()}.jpg"
    download_anchor_studio_image(
        anchor_gender=chosen_gender,
        category=resolved_cat,
        output_path=anchor_img_path,
    )

    scene_assets = []
    for idx, scene in enumerate(scenes):
        sid = scene.get("scene_id", idx + 1)
        audio_path = f"temp/voice_{sid}.mp3"
        img_path = f"temp/scene_{sid}.jpg"

        synthesize_broadcast_voice(
            text=scene.get("narration", ""),
            output_path=audio_path,
            category=resolved_cat,
            gender=chosen_gender,
            language=language,
        )

        download_scene_image(
            prompt=scene.get("image_prompt", ""),
            output_path=img_path,
            is_short=is_short,
            search_query=scene.get("search_query", ""),
            rss_image_url=scene.get("rss_image_url", ""),
            headline_text=scene.get("headline_banner", ""),
        )

        scene_assets.append({
            "scene_id": sid,
            "audio_path": audio_path,
            "image_path": img_path,
            "narration": scene.get("narration", ""),
            "subtitles": scene.get("subtitles", scene.get("narration", "")),
            "headline_banner": scene.get("headline_banner", script_data.get("headline_banner", "BREAKING NEWS")),
            "camera_angle": scene.get("camera_angle", "closeup" if idx % 2 == 1 else "wide"),
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "short" if is_short else "long"
    output_video = f"output/{prefix}_{resolved_cat.lower()}_{timestamp}.mp4"
    build_news_video(
        script_data=script_data,
        scene_assets=scene_assets,
        output_path=output_video,
        is_short=is_short,
        anchor_img_path=anchor_img_path,
    )

    logger.info(f"🎉 Broadcast Video Ready: {output_video}")
    if not skip_upload:
        upload_to_youtube(output_video, script_data, is_short=is_short)

    return output_video


def main():
    parser = argparse.ArgumentParser(description="24/7 Autonomous AI TV News Studio Bot")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument(
        "--type",
        choices=["short", "long", "both"],
        default="both",
        help="Video format: 'short' (9:16), 'long' (16:9), or 'both' (uploads 1 Short + 1 Long video)",
    )
    parser.add_argument("--category", default="AUTO", help="NATION, WORLD, TECHNOLOGY, or AUTO")
    parser.add_argument("--anchor", choices=["male", "female", "auto"], default="auto", help="Anchor gender")
    parser.add_argument("--breaking", action="store_true", help="Breaking news mode")
    parser.add_argument("--skip-upload", action="store_true", help="Render locally without YouTube upload")
    args = parser.parse_args()

    anchor_override = None if args.anchor == "auto" else args.anchor

    if args.once:
        if args.type in ("short", "both"):
            produce_news_episode(
                category=args.category,
                is_short=True,
                is_breaking=args.breaking,
                anchor_gender=anchor_override,
                skip_upload=args.skip_upload,
            )
        if args.type in ("long", "both"):
            produce_news_episode(
                category=args.category,
                is_short=False,
                is_breaking=args.breaking,
                anchor_gender=anchor_override,
                skip_upload=args.skip_upload,
            )
        return

    logger.info("📡 Starting 24/7 Autonomous TV News Loop...")
    while True:
        produce_news_episode(category=args.category, is_short=True, is_breaking=False, anchor_gender=anchor_override)
        if ENABLE_LONG_VIDEOS:
            produce_news_episode(category=args.category, is_short=False, is_breaking=False, anchor_gender=anchor_override)
        time.sleep(max(1, SHORTS_INTERVAL_HOURS) * 3600)


if __name__ == "__main__":
    main()
