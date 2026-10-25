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
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("NewsBot")

# ================= 1. CREDENTIALS & CONFIG =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "").strip()
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "").strip()
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "").strip()

CATEGORIES = ["NATION", "WORLD", "TECHNOLOGY"]
SHORTS_INTERVAL_HOURS = 3
ENABLE_LONG_VIDEOS = True
MIN_LONG_VIDEO_SECONDS = 605.0  # Guaranteed 10+ minutes (605s) for Long Videos

# Pure Hindi RSS feeds for NATION & TECHNOLOGY so Hindi bulletins NEVER get English headlines
NEWS_FEEDS = {
    "NATION": [
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
        "https://news.google.com/rss/search?q=%E0%A4%AD%E0%A4%BE%E0%A4%B0%E0%A4%A4+%E0%A4%AC%E0%A4%A1%E0%A4%BC%E0%A5%80+%E0%A4%96%E0%A4%AC%E0%A4%B0&hl=hi&gl=IN&ceid=IN:hi",
    ],
    "TECHNOLOGY": [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=hi&gl=IN&ceid=IN:hi",
        "https://news.google.com/rss/search?q=%E0%A4%9F%E0%A5%87%E0%A4%95%E0%A5%8D%E0%A4%A8%E0%A5%8B%E0%A4%B2%E0%A5%89%E0%A4%9C%E0%A5%80+OR+%E0%A4%8F%E0%A4%86%E0%A4%88&hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
    ],
    "WORLD": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.feedburner.com/ndtvnews-world-news",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
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
_FONT_CACHE = {}


def _pick_anchor_gender(override=None):
    global _ANCHOR_TOGGLE
    if override in ("male", "female"):
        return override
    gender = "female" if (_ANCHOR_TOGGLE % 2 == 0) else "male"
    _ANCHOR_TOGGLE += 1
    return gender


# ================= 2. CACHED BILINGUAL HINDI + ENGLISH FONT ENGINE =================
def _load_font_pair(size=36):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
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
    pair = ((deva_font or fallback), (latin_font or fallback))
    _FONT_CACHE[size] = pair
    return pair


def draw_bilingual_text(draw, xy, text, size=34, fill=(255, 255, 255)):
    """Routes Devanagari Hindi tokens to NotoSansDevanagari and English/ASCII tokens to DejaVuSans."""
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


def fetch_trending_news(category="NATION", max_items=16):
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
                norm_key = clean_title[:40].lower()
                if not clean_title or norm_key in seen_titles:
                    continue
                seen_titles.add(norm_key)

                headlines.append({
                    "title": clean_title,
                    "summary": desc[:350] if desc else clean_title,
                    "source": source,
                    "media_url": media_url,
                })
                if len(headlines) >= max_items:
                    break
        except Exception as e:
            logger.warning(f"RSS fetch warning ({url}): {e}")

    return headlines


def _call_gemini_rest(model_name, prompt, api_key, timeout_sec=40):
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


def _build_detailed_story_narration(idx, total, hl, language="hindi", is_short=True):
    """Creates an authoritative, professional broadcast narration for a story."""
    title = hl.get("title", "")
    summary = hl.get("summary", title)
    if summary.lower().startswith(title[:30].lower()):
        summary = title

    if language == "hindi":
        if is_short:
            if idx == 0:
                return f"नमस्कार, चौबीस घंटे लाइव न्यूज़ बुलेटिन में आपका स्वागत है। इस वक्त की सबसे बड़ी खबर: {title}।"
            elif idx == total - 1:
                return f"वहीं एक और अहम खबर: {title}। पल-पल के सटीक लाइव अपडेट्स के लिए हमारे चैनल को अभी सब्सक्राइब करें। नमस्कार।"
            else:
                return f"ताज़ा जानकारी के मुताबिक, {title}। प्रशासन और विशेषज्ञों की इस पूरे मामले पर कड़ी नज़र बनी हुई है।"
        else:
            # Detailed ~90-110 word segment for 10-minute Long Video Mega Bulletin
            if idx == 0:
                return (
                    f"नमस्कार, चौबीस घंटे लाइव न्यूज़ के प्राइम टाइम महाबुलेटिन में आपका स्वागत है। "
                    f"आज हम देश और दुनिया की तमाम बड़ी खबरों का विस्तार से विश्लेषण करेंगे। "
                    f"शुरुआत करते हैं इस वक्त की सबसे बड़ी और अहम खबर के साथ: {title}। "
                    f"विस्तृत रिपोर्ट के अनुसार, {summary}। "
                    f"इस पूरे घटनाक्रम को लेकर उच्च स्तर पर बैठकों का दौर जारी है और विशेषज्ञों का मानना है कि "
                    f"आने वाले दिनों में इसके बेहद महत्वपूर्ण परिणाम देखने को मिलेंगे। प्रशासन ने भी इस मामले में पूरी सतर्कता बरतने के निर्देश दिए हैं।"
                )
            elif idx == total - 1:
                return (
                    f"महाबुलेटिन के अंत में रुख करते हैं आज की एक और बड़ी खबर की ओर: {title}। "
                    f"ताज़ा अपडेट के मुताबिक, {summary}। "
                    f"इस विषय पर हमारे संवाददाताओं और विश्लेषकों की टीम लगातार ग्राउंड जीरो से हर अपडेट आप तक पहुँचा रही है। "
                    f"देश और दुनिया की हर बड़ी खबर को सबसे पहले और पूरी निष्पक्षता के साथ देखने के लिए हमारे चैनल को अभी सब्सक्राइब करें, "
                    f"वीडियो को लाइक करें और अपनी राय कमेंट बॉक्स में ज़रूर लिखें। अभी के लिए बस इतना ही, नमस्कार।"
                )
            else:
                transitions = [
                    "अब बढ़ते हैं आज की अगली बड़ी खबर की ओर",
                    "वहीं दूसरी तरफ एक और बेहद अहम घटनाक्रम सामने आ रहा है",
                    "प्राइम टाइम बुलेटिन में अब बात करते हैं इस वक्त की बड़ी अपडेट की",
                    "इसके साथ ही देश से जुड़ी एक और महत्वपूर्ण खबर पर नज़र डालते हैं",
                    "आगे बढ़ते हैं और देखते हैं यह विशेष रिपोर्ट",
                ]
                tr = transitions[idx % len(transitions)]
                return (
                    f"{tr}। खबर है कि {title}। "
                    f"आधिकारिक सूत्रों और ताज़ा रिपोर्ट के मुताबिक, {summary}। "
                    f"आपको बता दें कि इस मुद्दे को लेकर पिछले कई घंटों से लगातार चर्चा तेज़ है और संबंधित विभाग द्वारा "
                    f"स्थिति की गहन समीक्षा की जा रही है। जानकारों के अनुसार आम नागरिकों और व्यवस्था पर इसका सीधा और व्यापक असर पड़ने की संभावना है, "
                    f"जिसको ध्यान में रखते हुए आगे की रणनीति तैयार की जा रही है।"
                )
    else:
        if is_short:
            if idx == 0:
                return f"Welcome to our 24/7 Live Global News bulletin. Our top breaking story right now: {title}."
            elif idx == total - 1:
                return f"Meanwhile, {title}. Subscribe now for continuous breaking updates from our global newsroom."
            else:
                return f"According to the latest official dispatches, {title}. Authorities and analysts are closely monitoring the situation."
        else:
            if idx == 0:
                return (
                    f"Good evening and welcome to our Prime-Time Global News Special Report. "
                    f"Over the next ten minutes, we bring you comprehensive coverage and in-depth analysis of the biggest stories shaping our world today. "
                    f"We begin with our top breaking headline this hour: {title}. "
                    f"According to official dispatches and correspondents on the ground, {summary}. "
                    f"Senior diplomatic and policy analysts note that this development marks a critical turning point, "
                    f"with emergency consultations currently underway across major international capitals to assess the immediate strategic impact."
                )
            elif idx == total - 1:
                return (
                    f"Finally, rounding out our special prime-time broadcast tonight: {title}. "
                    f"Latest reports confirm that {summary}. "
                    f"Our global network of correspondents will continue to track every angle of these developing stories throughout the day and night. "
                    f"Thank you for watching our 24/7 Live News broadcast. Be sure to subscribe to the channel and share your thoughts in the comments below. Goodnight."
                )
            else:
                transitions = [
                    "Turning now to another major international development",
                    "Meanwhile, our global news desk is closely tracking this breaking story",
                    "In other significant news making headlines around the world tonight",
                    "Shifting focus to a critical update from our international bureau",
                    "Continuing our special prime-time coverage with this developing report",
                ]
                tr = transitions[idx % len(transitions)]
                return (
                    f"{tr}: {title}. "
                    f"Detailed reports indicate that {summary}. "
                    f"International observers and market specialists have been closely evaluating the fallout of this situation over the past several hours. "
                    f"Officials have emphasized that coordinated measures are being implemented to maintain stability, "
                    f"while independent experts warn that the long-term geopolitical and economic implications will be closely watched in the days ahead."
                )


def _build_local_fallback_script(category, headlines, is_short, is_breaking, anchor_gender, language):
    if not headlines:
        headlines = [{
            "title": "भारत और दुनिया की इस वक्त की सबसे बड़ी खबरें" if language == "hindi" else "Major Global Breaking News Developments Today",
            "summary": "राष्ट्रीय और अंतरराष्ट्रीय स्तर पर आज कई अहम फैसले लिए गए हैं।" if language == "hindi" else "Key diplomatic and economic decisions are unfolding across major capitals.",
            "source": "News Bureau",
            "media_url": "",
        }]

    target_count = 4 if is_short else 14
    expanded_headlines = []
    while len(expanded_headlines) < target_count:
        for h in headlines:
            expanded_headlines.append(h)
            if len(expanded_headlines) >= target_count:
                break

    top_title = expanded_headlines[0]["title"]
    banner = ("बड़ी ख़बर: महाबुलेटिन" if not is_short else "बड़ी ख़बर: लाइव अपडेट") if language == "hindi" else "BREAKING NEWS: LIVE REPORT"

    scenes = []
    for idx, hl in enumerate(expanded_headlines):
        kw = hl.get("title", top_title)
        nar = _build_detailed_story_narration(idx, len(expanded_headlines), hl, language=language, is_short=is_short)
        scenes.append({
            "scene_id": idx + 1,
            "narration": nar,
            "subtitles": nar,
            "headline_banner": kw[:68],
            "search_query": kw,
            "rss_image_url": hl.get("media_url", ""),
            "image_prompt": (
                f"Wide-angle realistic television news photojournalism of {kw}, "
                f"BBC and Reuters editorial broadcast photography, natural lighting, 8k DSLR, no text, no words, no charts"
            ),
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    ticker_items = [h["title"] for h in headlines[:8]]
    return {
        "category": category,
        "language": language,
        "anchor_gender": anchor_gender,
        "is_breaking": is_breaking,
        "is_short": is_short,
        "title": f"🔴 LIVE: {top_title[:75]} #Shorts" if is_short else f"🔴 LIVE महाबुलेटिन: Top 15 बड़ी ख़बरें | {top_title[:52]}",
        "description": (
            f"{top_title}\n\n"
            f"Watch 24x7 Live News updates in Aaj Tak, News 24 & BBC broadcast style.\n"
            f"{'#BreakingNews #LiveNews #HindiNews #Shorts' if is_short else '#BreakingNews #LiveNews #HindiNews #SpecialReport #FullBulletin'}"
        ),
        "tags": ["Breaking News", "Live News", "Hindi News", "Aaj Tak", "News 24", "BBC News", category] + (["Shorts"] if is_short else ["Special Report", "Full Bulletin"]),
        "headline_banner": banner,
        "ticker_text": "  |  ".join(ticker_items),
        "scenes": scenes,
        "raw_headlines": headlines,
    }


def generate_news_script(category=None, is_short=True, is_breaking=False, anchor_gender=None):
    if not category or category == "AUTO":
        category = random.choice(CATEGORIES)

    cat_upper = category.upper()
    language = "english" if cat_upper == "WORLD" else "hindi"
    chosen_gender = _pick_anchor_gender(anchor_gender)
    headlines = fetch_trending_news(cat_upper, max_items=16)

    # For 10+ minute Long Videos, use the multi-story Mega Bulletin builder
    if not is_short:
        logger.info(f"Building 14-Story Prime-Time Mega Bulletin (10+ Min Target) for {cat_upper} ({language})...")
        return _build_local_fallback_script(cat_upper, headlines, is_short=False, is_breaking=is_breaking, anchor_gender=chosen_gender, language=language)

    headlines_context = "\n".join(
        [f"{i+1}. Headline: {h['title']} | Details: {h['summary']}" for i, h in enumerate(headlines[:6])]
    ) or "1. भारत और दुनिया की बड़ी खबरें"

    if language == "hindi":
        lang_instruction = (
            "Write ALL `narration`, `subtitles`, `headline_banner`, and `ticker_text` strictly in PURE DEVANAGARI HINDI "
            "(देवनागरी लिपि, e.g., 'नमस्कार, इस वक्त की सबसे बड़ी खबर आ रही है...'). "
            "NEVER put English sentences in `headline_banner` or `narration`!"
        )
    else:
        lang_instruction = (
            "Write ALL `narration`, `subtitles`, `headline_banner`, and `ticker_text` in crisp BBC World News English."
        )

    prompt = f"""You are the Executive Producer for a 24/7 Live Television News Network (BBC News, Aaj Tak, News 24 style).
Create a 4-scene YouTube Short (9:16) TV news script from these live headlines:
{headlines_context}

CRITICAL RULES:
1. {lang_instruction}
2. Anchor Gender: "{chosen_gender}".
3. Total scenes: EXACTLY 4. Each scene's `narration` must be 20 to 28 words.
4. Return ONLY valid JSON with this exact structure:
{{
  "title": "Catchy YouTube title (max 85 chars, include #Shorts)",
  "description": "YouTube description with summary and hashtags",
  "tags": ["Breaking News", "Live News", "Shorts"],
  "headline_banner": "Main top story strap in {'Devanagari Hindi' if language=='hindi' else 'English'} (4-7 words)",
  "ticker_text": "4-5 top headlines separated by | in {'Devanagari Hindi' if language=='hindi' else 'English'}",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "...",
      "subtitles": "...",
      "headline_banner": "...",
      "search_query": "4-6 English keywords for event photo",
      "image_prompt": "Wide-angle realistic news photojournalism of the event, no text, no charts",
      "camera_angle": "wide"
    }}
  ]
}}"""

    if GEMINI_API_KEY:
        for model_name in ["gemini-3.8-flash", "gemini-2.5-flash"]:
            try:
                logger.info(f"Requesting SHORT script from {model_name} (lang={language}, anchor={chosen_gender})...")
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
                    if not sc.get("headline_banner"):
                        sc["headline_banner"] = hl.get("title", "बड़ी ख़बर")[:55]
                    if not sc.get("camera_angle"):
                        sc["camera_angle"] = "closeup" if idx % 2 == 1 else "wide"
                data["category"] = cat_upper
                data["language"] = language
                data["anchor_gender"] = chosen_gender
                data["is_breaking"] = is_breaking
                data["is_short"] = True
                data["raw_headlines"] = headlines
                logger.info(f"✅ Generated {len(scenes)}-scene {language.upper()} script via {model_name}")
                return data
            except Exception as e:
                logger.warning(f"Model {model_name} fallback: {e}")
                time.sleep(1)

    return _build_local_fallback_script(cat_upper, headlines, is_short=True, is_breaking=is_breaking, anchor_gender=chosen_gender, language=language)


# ================= 4. NEURAL VOICE ENGINE =================
async def _edge_tts_save(text, voice, rate, output_path):
    import edge_tts
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="+0Hz")
    await asyncio.wait_for(comm.save(output_path), timeout=35.0)


def synthesize_broadcast_voice(text, output_path, category="NATION", gender="female", language="hindi"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    clean_text = (text or "").strip() or "नमस्कार, ताज़ा खबरों के लिए हमारे साथ जुड़े रहिए।"
    cat_upper = (category or "NATION").upper()
    g_key = "male" if str(gender).lower() == "male" else "female"

    if str(language).lower() == "english" or cat_upper == "WORLD":
        voice = VOICE_MAP["WORLD"][g_key]
        rate = "+5%"
        lang_code = "en"
    else:
        voice = VOICE_MAP["NATION"][g_key]
        rate = "+7%"
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

    est_sec = max(6.0, len(clean_text.split()) / 2.3)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
            "-t", f"{est_sec:.1f}", "-af", "volume=0.02", output_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )
    return output_path


# ================= 5. REAL EVENT PHOTO & ANCHOR STUDIO ENGINE =================
def _validate_and_resize_image(raw_bytes, target_w, target_h):
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size
    if w < 250 or h < 200:
        raise ValueError("Image too small")
    arr = np.asarray(img, dtype=np.float32)
    if arr.std() < 12.0:
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
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.08)
    return img


def _fetch_pollinations_image(prompt, target_w, target_h):
    gen_w, gen_h = 1024, 1024
    clean_prompt = re.sub(r"[^\w\s,.-]", " ", prompt or "Editorial news photojournalism").strip()
    encoded = urllib.parse.quote(clean_prompt[:280])
    for model in ["flux", "turbo"]:
        seed = random.randint(1000, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&seed={seed}&model={model}&nologo=true"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=22)
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

    card_w, card_h = int(width * 0.86), int(height * 0.46)
    x0, y0 = (width - card_w) // 2, (height - card_h) // 2 + 20
    draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=18, fill=(18, 26, 52), outline=(255, 195, 0), width=4)
    draw.rectangle([x0, y0, x0 + card_w, y0 + 54], fill=(195, 18, 30))
    draw.ellipse([x0 + 22, y0 + 17, x0 + 42, y0 + 37], fill=(255, 255, 255))
    draw_bilingual_text(draw, (x0 + 54, y0 + 11), "LIVE SATELLITE NEWS FEED  |  24x7", size=26, fill=(255, 255, 255))

    clean_hl = (headline_text or "LIVE BREAKING NEWS UPDATE").strip()
    words = clean_hl.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= 28:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    ty = y0 + 76
    for line in lines[:3]:
        draw_bilingual_text(draw, (x0 + 28, ty), line, size=32, fill=(255, 245, 215))
        ty += 48

    img.save(output_path, "JPEG", quality=92)
    return output_path


def download_scene_image(prompt, output_path, is_short=True, search_query="", rss_image_url="", headline_text=""):
    """
    Fetches authentic RSS media image or generates custom photorealistic news B-roll via Pollinations Flux.
    Does NOT scrape random web charts/logos from Bing so B-roll always looks like real TV news footage!
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w = 1080 if is_short else 880
    target_h = 880 if is_short else 600

    # 1. Official RSS news article photo if high-res
    if rss_image_url and rss_image_url.startswith("http"):
        try:
            resp = requests.get(rss_image_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 18000:
                img = _validate_and_resize_image(resp.content, target_w, target_h)
                img.save(output_path, "JPEG", quality=92)
                return output_path
        except Exception:
            pass

    # 2. Custom photorealistic editorial news B-roll (1024x1024 Flux)
    logger.info(f"🎨 Generating Photorealistic News B-Roll ({target_w}x{target_h})...")
    full_prompt = (
        f"{prompt}, realistic television news broadcast camera footage, "
        f"wide angle photojournalism, natural lighting, 8k UHD, strictly no text, no words, no charts, no logos"
    )
    img = _fetch_pollinations_image(full_prompt, target_w, target_h)
    if img is not None:
        img.save(output_path, "JPEG", quality=92)
        return output_path

    return _create_broadcast_broll_graphic(output_path, target_w, target_h, headline_text=headline_text or search_query)


def _create_procedural_studio_anchor(output_path, anchor_gender="female", width=1024, height=1024):
    img = Image.new("RGB", (width, height), (14, 18, 34))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        r = int(14 + 28 * (y / float(height)))
        g = int(20 + 18 * (y / float(height)))
        b = int(42 + 45 * (y / float(height)))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    for y_bar in [110, 220, 330, 440]:
        draw.rectangle([40, y_bar, width - 40, y_bar + 6], fill=(200, 30, 45))
        draw.rectangle([80, y_bar + 12, width - 80, y_bar + 16], fill=(0, 170, 240))

    cx = width // 2
    suit_color = (22, 28, 48) if anchor_gender == "male" else (155, 22, 38)
    draw.polygon([(cx - 280, height), (cx + 280, height), (cx + 210, 460), (cx - 210, 460)], fill=suit_color)
    draw.polygon([(cx - 55, 460), (cx + 55, 460), (cx, 660)], fill=(242, 245, 250))
    if anchor_gender == "male":
        draw.polygon([(cx - 18, 480), (cx + 18, 480), (cx + 24, 650), (cx - 24, 650)], fill=(195, 20, 32))

    skin = (224, 172, 138)
    draw.rectangle([cx - 42, 375, cx + 42, 485], fill=skin)
    draw.ellipse([cx - 110, 165, cx + 110, 425], fill=skin)

    if anchor_gender == "female":
        draw.pieslice([cx - 124, 140, cx + 124, 400], 160, 380, fill=(24, 18, 16))
        draw.polygon([(cx - 120, 250), (cx - 95, 475), (cx - 65, 460)], fill=(24, 18, 16))
        draw.polygon([(cx + 120, 250), (cx + 95, 475), (cx + 65, 460)], fill=(24, 18, 16))
    else:
        draw.pieslice([cx - 116, 145, cx + 116, 330], 175, 365, fill=(22, 18, 16))

    eye_y = 280
    for ex in [cx - 44, cx + 44]:
        draw.ellipse([ex - 20, eye_y - 9, ex + 20, eye_y + 9], fill=(250, 250, 250))
        draw.ellipse([ex - 8, eye_y - 8, ex + 8, eye_y + 8], fill=(38, 26, 20))
        draw.ellipse([ex - 3, eye_y - 3, ex + 3, eye_y + 3], fill=(255, 255, 255))
        draw.arc([ex - 24, eye_y - 20, ex + 24, eye_y - 4], 190, 350, fill=(28, 20, 18), width=4)

    draw.line([(cx, 285), (cx - 6, 338), (cx + 8, 342)], fill=(185, 132, 102), width=3)
    mouth_y = 370
    lip_col = (185, 55, 68) if anchor_gender == "female" else (165, 78, 74)
    draw.polygon([(cx - 36, mouth_y), (cx, mouth_y - 8), (cx + 36, mouth_y), (cx, mouth_y + 11)], fill=lip_col)
    draw.line([(cx - 32, mouth_y), (cx + 32, mouth_y)], fill=(90, 25, 30), width=2)
    img.save(output_path, "JPEG", quality=94)
    return output_path


# ================= 6. 100% PURE-NUMPY FACE, EYE & LIP DETECTOR (NO OPENCV NEEDED) =================
def detect_face_eyes_mouth_pure_numpy(rgb_arr):
    """
    100% Pure-NumPy 2D Face, Symmetric Eye-Pair, and Lip Detector (ZERO cv2 dependency!).
    Finds the exact face bounding box, left & right eye coordinates, and lip line on any portrait.
    """
    h, w, _ = rgb_arr.shape
    r = rgb_arr[:, :, 0].astype(np.float32)
    g = rgb_arr[:, :, 1].astype(np.float32)
    b = rgb_arr[:, :, 2].astype(np.float32)
    luma = 0.299 * r + 0.587 * g + 0.114 * b

    # 1. Detect warm skin mask in upper 82% of frame
    skin = (
        (r > 85)
        & (g > 40)
        & (b > 20)
        & ((r - g) > 10)
        & ((r - b) > 18)
        & (r < 252)
        & (luma > 55)
        & (luma < 235)
    ).astype(np.float32)
    skin[int(h * 0.82) :, :] = 0.0
    skin[:, : int(w * 0.12)] = 0.0
    skin[:, int(w * 0.88) :] = 0.0

    row_skin = np.mean(skin, axis=1)
    col_skin = np.mean(skin, axis=0)
    ys = np.where(row_skin > 0.07)[0]
    xs = np.where(col_skin > 0.07)[0]

    if len(ys) > 30 and len(xs) > 30:
        fy = int(ys[0])
        fw = int(min(w * 0.52, max(w * 0.18, xs[-1] - xs[0])))
        fh = int(min(h * 0.62, max(h * 0.22, fw * 1.18)))
        cx_vals = np.arange(w, dtype=np.float32)
        face_band_skin = np.mean(skin[fy : min(h, fy + fh), :], axis=0)
        cx = int(np.sum(cx_vals * face_band_skin) / max(1e-5, np.sum(face_band_skin)))
        fx = max(0, min(w - fw, cx - fw // 2))
    else:
        fw, fh = int(w * 0.30), int(h * 0.36)
        fx, fy = (w - fw) // 2, int(h * 0.12)

    # 2. 2D Symmetric Eye-Pair Search inside Upper Face [fy + 0.24*fh .. fy + 0.52*fh]
    ey_min = max(4, fy + int(fh * 0.24))
    ey_max = min(h - 10, fy + int(fh * 0.52))
    gy = np.abs(np.diff(luma, axis=0, prepend=luma[:1, :]))
    eye_feat = gy * (220.0 - np.clip(luma, 40.0, 220.0))

    best_score = -1.0
    best_ey = fy + int(fh * 0.38)
    best_cx = fx + fw // 2
    best_d = int(fw * 0.21)

    d_min = max(14, int(fw * 0.15))
    d_max = max(d_min + 4, int(fw * 0.27))
    cx_min = max(d_max + 6, fx + int(fw * 0.38))
    cx_max = min(w - d_max - 6, fx + int(fw * 0.62))

    for ey in range(ey_min, ey_max, 2):
        strip = np.mean(eye_feat[max(0, ey - 4) : min(h, ey + 5), :], axis=0)
        for cx_try in range(cx_min, max(cx_min + 1, cx_max), 3):
            for d in range(d_min, d_max, 3):
                lx, rx_pos = cx_try - d, cx_try + d
                l_val = np.mean(strip[max(0, lx - 6) : min(w, lx + 7)])
                r_val = np.mean(strip[max(0, rx_pos - 6) : min(w, rx_pos + 7)])
                bridge_val = np.mean(strip[max(0, cx_try - 4) : min(w, cx_try + 5)])
                sym_penalty = abs(l_val - r_val) * 0.5
                score = (l_val + r_val) - 0.65 * bridge_val - sym_penalty
                if score > best_score:
                    best_score = score
                    best_ey = ey
                    best_cx = cx_try
                    best_d = d

    rx_e = max(11, int(best_d * 0.42))
    ry_e = max(6, int(rx_e * 0.58))
    eye_boxes = [
        (best_cx - best_d, best_ey, rx_e, ry_e),
        (best_cx + best_d, best_ey, rx_e, ry_e),
    ]

    # 3. Exact Mouth Center inside [best_ey + 1.35*best_d .. best_ey + 2.15*best_d]
    my_min = max(best_ey + int(best_d * 1.35), fy + int(fh * 0.64))
    my_max = min(h - 8, max(my_min + 10, best_ey + int(best_d * 2.15)))
    mx0 = max(0, best_cx - int(best_d * 0.85))
    mx1 = min(w, best_cx + int(best_d * 0.85))

    if my_max > my_min and mx1 > mx0:
        r_m = r[my_min:my_max, mx0:mx1]
        g_m = g[my_min:my_max, mx0:mx1]
        gy_m = gy[my_min:my_max, mx0:mx1]
        l_m = luma[my_min:my_max, mx0:mx1]
        lip_row_score = np.mean((r_m - 1.1 * g_m) + 0.65 * gy_m - 0.20 * l_m, axis=1)
        mouth_y = my_min + int(np.argmax(lip_row_score))
    else:
        mouth_y = best_ey + int(best_d * 1.72)

    mouth_x = best_cx
    mouth_w = max(15, int(best_d * 0.82))
    mouth_h = max(6, int(mouth_w * 0.32))

    # Refine face_box around best_cx, best_ey, mouth_y
    ref_fh = max(60, int((mouth_y - best_ey) * 2.35))
    ref_fw = max(55, int(best_d * 4.6))
    ref_fx = max(0, min(w - ref_fw, best_cx - ref_fw // 2))
    ref_fy = max(0, best_ey - int(ref_fh * 0.38))
    face_box = (ref_fx, ref_fy, ref_fw, ref_fh)

    return face_box, eye_boxes, (mouth_x, mouth_y, mouth_w, mouth_h)


def download_anchor_studio_image(anchor_gender="female", category="NATION", output_path="temp/anchor_studio.jpg"):
    """
    Fetches a photorealistic Male or Female Indian/Global TV News Anchor waist-up medium shot
    with flat symmetrical front lighting so both eyes and lips are clearly visible and well-proportioned.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w, target_h = 1024, 1024
    gender_word = "real Indian male" if str(anchor_gender).lower() == "male" else "real Indian female"
    attire = (
        "wearing a dark navy business suit, white shirt, and red tie, lapel microphone"
        if str(anchor_gender).lower() == "male"
        else "wearing a professional crimson-red blazer over dark top, lapel microphone"
    )
    if str(category).upper() == "WORLD":
        gender_word = "real international male" if str(anchor_gender).lower() == "male" else "real international female"

    prompt = (
        f"Medium waist-up shot of a {gender_word} television news anchor {attire}, "
        f"sitting behind a modern BBC and Aaj Tak live broadcast newsroom desk, "
        f"full shoulders and torso visible, looking straight into camera lens with composed expression, "
        f"flat even symmetrical front television studio lighting on whole face, both eyes clearly lit, "
        f"head centered in upper-middle frame occupying 28 percent of height, "
        f"blurred red and blue newsroom LED screens in background, 8k DSLR broadcast camera, no text"
    )
    logger.info(f"🧑‍💼 Fetching photorealistic {anchor_gender.upper()} TV News Anchor for {category}...")
    for attempt in range(2):
        img = _fetch_pollinations_image(prompt, target_w, target_h)
        if img is not None:
            img.save(output_path, "JPEG", quality=94)
            return output_path
    return _create_procedural_studio_anchor(output_path, anchor_gender=anchor_gender, width=target_w, height=target_h)


def _prepare_studio_anchor_canvas(anchor_img_path, width, height, desk_ratio=0.72):
    """
    Auto-frames any anchor portrait to fill 100% of the studio window width with full headroom
    above the head (never clipping the forehead or showing side borders) + 3D Broadcast Desk!
    Uses 100% Pure-NumPy Face/Eye/Mouth detection (zero OpenCV dependency).
    """
    raw = Image.open(anchor_img_path).convert("RGB")
    bg = Image.new("RGB", (width, height), (12, 18, 38))
    desk_y = int(height * desk_ratio)
    target_h_top = desk_y + 12

    rw, rh = raw.size
    raw_arr = np.asarray(raw, dtype=np.uint8)
    raw_face_box, _, _ = detect_face_eyes_mouth_pure_numpy(raw_arr)
    fx, fy, fw, fh = raw_face_box

    scale = max(width / float(rw), target_h_top / float(rh))
    # If the face is huge (close-up), keep headroom and pad sides with blurred studio background
    if (fh * scale) > (target_h_top * 0.54):
        scale = (target_h_top * 0.50) / float(max(1, fh))

    new_w = max(1, int(rw * scale))
    new_h = max(1, int(rh * scale))
    scaled = raw.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Fill background with blurred stretched studio backdrop so there are NEVER hard side bars
    backdrop = raw.resize((width, target_h_top), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(22))
    backdrop = ImageEnhance.Brightness(backdrop).enhance(0.55)
    bg.paste(backdrop, (0, 0))

    sc_cx = int((fx + fw * 0.5) * scale)
    sc_fy = int(fy * scale)
    paste_x = (width // 2) - sc_cx
    ideal_top_y = max(6, int(target_h_top * 0.14) - sc_fy)
    paste_y = min(0, ideal_top_y) if new_h >= target_h_top else max(0, target_h_top - new_h)

    mask = Image.new("L", (new_w, new_h), 255)
    if new_w < width:
        m_draw = ImageDraw.Draw(mask)
        m_draw.rectangle([0, 0, new_w - 1, new_h - 1], outline=0, width=24)
        mask = mask.filter(ImageFilter.GaussianBlur(14))
    bg.paste(scaled, (paste_x, paste_y), mask)

    # Draw 3D Broadcast News Desk from desk_y to height (eliminates any bottom black void!)
    d_draw = ImageDraw.Draw(bg)
    d_draw.polygon([(0, desk_y), (width, desk_y), (width, height), (0, height)], fill=(12, 18, 38))
    d_draw.rectangle([0, desk_y, width, desk_y + 7], fill=(250, 198, 0))
    d_draw.rectangle([0, desk_y + 7, width, desk_y + 14], fill=(195, 16, 30))

    # Dual Broadcast Condenser Microphones on Desk
    for side in [-1, 1]:
        mx = (width // 2) + side * int(width * 0.17)
        d_draw.line([(mx, desk_y), (mx - side * 16, desk_y - 44)], fill=(55, 62, 75), width=5)
        d_draw.ellipse([mx - side * 16 - 9, desk_y - 58, mx - side * 16 + 9, desk_y - 36], fill=(28, 32, 40), outline=(200, 210, 225), width=2)

    # Detect exact face, eyes, and mouth on the final composited studio frame (above desk_y)
    comp_arr = np.asarray(bg, dtype=np.uint8)
    upper_arr = comp_arr[:desk_y, :, :]
    face_box, eye_boxes, mouth_info = detect_face_eyes_mouth_pure_numpy(upper_arr)

    return comp_arr, face_box, eye_boxes, mouth_info, desk_y


class BroadcastAnchorAnimator:
    """
    Ultra-fast, Photorealistic ROI-Patch Anchor Animator (100% Pure NumPy, ZERO OpenCV needed):
      - Animates ONLY the exact detected Left/Right Eye patches (natural upper-eyelid squeeze blink)
      - Animates ONLY the exact detected Mouth/Chin patch (speech-synced lip & jaw articulation)
      - Zero nose/cheek distortion, runs at >500 fps!
    """

    def __init__(self, anchor_img_path, width=1080, height=980, desk_ratio=0.66):
        self.w = width
        self.h = height
        self.base, self.face_box, self.eye_boxes, self.mouth_info, self.desk_y = _prepare_studio_anchor_canvas(
            anchor_img_path, width, height, desk_ratio=desk_ratio
        )
        self.fx, self.fy, self.fw, self.fh = self.face_box
        self.mx, self.my, self.mw, self.mh = self.mouth_info

        # Precompute mouth ROI meshgrid once so per-frame lip-sync takes <0.3ms
        self.m_y0 = max(0, self.my - 4)
        self.m_y1 = min(self.desk_y, self.fy + int(self.fh * 1.06))
        self.m_x0 = max(0, self.mx - int(self.mw * 1.6))
        self.m_x1 = min(self.w, self.mx + int(self.mw * 1.6))
        yy, xx = np.meshgrid(
            np.arange(self.m_y0, self.m_y1, dtype=np.float32),
            np.arange(self.m_x0, self.m_x1, dtype=np.float32),
            indexing="ij",
        )
        self.m_xx = xx.astype(np.int32)
        self.m_yy = yy
        jaw_cy = self.my + self.mh * 1.4
        self.jaw_mask = np.exp(-(((xx - self.mx) / max(1.0, self.mw * 1.1)) ** 2 + ((yy - jaw_cy) / max(1.0, self.mh * 2.2)) ** 2))

        # Oral opening mask
        self.open_rx = max(6, int(self.mw * 0.72))
        self.open_ry = max(3, int(self.mh * 0.75))
        self.o_y0 = max(0, self.my - self.open_ry)
        self.o_y1 = min(self.desk_y, self.my + self.open_ry + 2)
        self.o_x0 = max(0, self.mx - self.open_rx)
        self.o_x1 = min(self.w, self.mx + self.open_rx)
        oyy, oxx = np.meshgrid(
            np.arange(self.o_y0, self.o_y1, dtype=np.float32),
            np.arange(self.o_x0, self.o_x1, dtype=np.float32),
            indexing="ij",
        )
        self.oral_mask = np.exp(
            -(((oxx - self.mx) / max(1.0, self.open_rx * 0.75)) ** 2 + ((oyy - (self.my + 1)) / max(1.0, self.open_ry * 0.85)) ** 2)
        )[:, :, None]

        # Precompute eye blink meshgrids
        self.eye_patches = []
        for (ecx, ecy, rx, ry) in self.eye_boxes:
            ey0 = max(0, ecy - int(ry * 1.4))
            ey1 = min(self.desk_y, ecy + int(ry * 1.15))
            ex0 = max(0, ecx - int(rx * 1.25))
            ex1 = min(self.w, ecx + int(rx * 1.25))
            eyy, exx = np.meshgrid(
                np.arange(ey0, ey1, dtype=np.float32),
                np.arange(ex0, ex1, dtype=np.float32),
                indexing="ij",
            )
            horiz = np.clip(1.0 - ((exx - ecx) / max(1.0, rx * 1.05)) ** 2, 0.0, 1.0)
            vert = np.exp(-((eyy - ecy) / max(1.0, ry * 0.85)) ** 2)
            pull_unit = (ry * 1.25) * horiz * vert
            self.eye_patches.append((ey0, ey1, ex0, ex1, exx.astype(np.int32), eyy, pull_unit))

    def render_frame(self, t, speech_amp):
        frame = self.base.copy()

        # 1. Natural Periodic Eye Blink (every 3.8s, smooth 0.14s upper-eyelid squeeze)
        blink_phase = t % 3.8
        blink_amount = math.exp(-((blink_phase - 1.9) / 0.055) ** 2)
        if blink_amount > 0.06:
            for (ey0, ey1, ex0, ex1, exx, eyy, pull_unit) in self.eye_patches:
                src_y = np.clip(np.rint(eyy - blink_amount * pull_unit).astype(np.int32), 0, self.h - 1)
                frame[ey0:ey1, ex0:ex1] = self.base[src_y, exx]

        # 2. Speech-Synced Mouth & Lower-Jaw Articulation
        if speech_amp > 0.08:
            mod = 0.85 + 0.15 * math.sin(t * 11.0)
            eff_amp = min(1.0, speech_amp * mod)
            drop_px = 4.2 * eff_amp * self.jaw_mask
            src_y = np.clip(np.rint(self.m_yy - drop_px).astype(np.int32), 0, self.h - 1)
            frame[self.m_y0 : self.m_y1, self.m_x0 : self.m_x1] = frame[src_y, self.m_xx]

            oral_region = frame[self.o_y0 : self.o_y1, self.o_x0 : self.o_x1].astype(np.float32)
            oral_region *= 1.0 - (0.60 * eff_amp * self.oral_mask)
            frame[self.o_y0 : self.o_y1, self.o_x0 : self.o_x1] = np.clip(oral_region, 0, 255).astype(np.uint8)

        return frame


# ================= 7. FULL-FRAME BROADCAST VIDEO RENDERER =================
def _get_audio_duration(audio_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        return max(2.0, float(out))
    except Exception:
        return 6.5


def _extract_audio_envelope(audio_path, duration, fps=20):
    n_frames = max(1, int(math.ceil(duration * fps)) + 2)
    sample_rate = 1200
    try:
        cmd = ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
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


def _split_caption_chunks(text, max_words_per_chunk=7):
    words = (text or "").strip().split()
    if not words:
        return [""]
    return [" ".join(words[i : i + max_words_per_chunk]) for i in range(0, len(words), max_words_per_chunk)]


def _create_bgm_wav(total_duration, bgm_path="temp/broadcast_bgm.wav"):
    import wave
    sr = 16000
    loop_sec = min(20.0, total_duration)
    n_loop = int(loop_sec * sr)
    t = np.linspace(0, loop_sec, n_loop, endpoint=False)
    pad = 0.35 * np.sin(2 * np.pi * 110.0 * t) + 0.25 * np.sin(2 * np.pi * 165.0 * t)
    pulse = (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)) ** 3
    beeps = 0.20 * np.sin(2 * np.pi * 440.0 * t) * pulse
    wave_loop = np.clip((pad + beeps) * 0.04, -0.9, 0.9)
    pcm_loop = (wave_loop * 32767).astype(np.int16)
    repeats = int(math.ceil(total_duration / max(1.0, loop_sec)))
    full_pcm = np.tile(pcm_loop, repeats)[: int(total_duration * sr)]

    os.makedirs(os.path.dirname(os.path.abspath(bgm_path)), exist_ok=True)
    with wave.open(bgm_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(full_pcm.tobytes())
    return bgm_path if os.path.exists(bgm_path) else None


def build_news_video(script_data, scene_assets, output_path, is_short=True, anchor_img_path=None):
    """
    Renders a full-bleed BBC / Aaj Tak / News 24 broadcast video:
      - Short (1080x1920 @ 24fps): Zero bottom black bars; 3D Studio Desk houses subtitles, ticker, and desk pedestal.
      - Long Video (1280x720 16:9 HD @ 20fps): Fast zero-copy streaming for 10+ minute Mega Bulletins!
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    fps = 24 if is_short else 20
    W, H = (1080, 1920) if is_short else (1280, 720)

    language = script_data.get("language", "hindi")
    category = script_data.get("category", "NATION").upper()
    ticker_raw = script_data.get("ticker_text") or script_data.get("headline_banner") or "LIVE BREAKING NEWS UPDATES"

    ticker_clean = re.sub(r"•", " | ", ticker_raw)
    ticker_unit = f"   [LIVE 24x7]  {ticker_clean}   |   BREAKING NEWS   |   "
    ticker_full = ticker_unit * 4

    ticker_h = 58 if is_short else 44
    ticker_font_sz = 30 if is_short else 23
    ticker_w = max(W * 4, len(ticker_full) * 18)
    ticker_strip = Image.new("RGB", (ticker_w, ticker_h), (248, 198, 0))
    t_draw = ImageDraw.Draw(ticker_strip)
    t_draw.rectangle([0, 0, ticker_w, 4], fill=(190, 15, 25))
    end_x = draw_bilingual_text(t_draw, (20, (ticker_h - ticker_font_sz) // 2 - 2), ticker_full, size=ticker_font_sz, fill=(10, 12, 18))
    unit_px = max(450, (end_x - 20) // 4)
    ticker_arr = np.asarray(ticker_strip, dtype=np.uint8)

    if is_short:
        # 9:16 Vertical Full-Bleed Layout (1080x1920) - ZERO BLACK SPACE!
        broll_win_w, broll_win_h = W, 830
        strap_h = 104
        anchor_w, anchor_h = W, H - broll_win_h - strap_h  # 986px (fills y=934..1920 completely!)
        sub_h = 96
        max_words_chunk = 6
        hl_max_chars = 42
        desk_ratio = 0.56  # Desk starts at y = 934 + 552 = 1486, housing subtitles, ticker, and desk pedestal!
    else:
        # 16:9 Horizontal Prime-Time TV Layout (1280x720)
        header_h = 46
        strap_h = 58
        sub_h = 58
        body_h = H - header_h - strap_h - sub_h - ticker_h  # 514px (y=46..560)
        broll_win_w, broll_win_h = 760, body_h
        anchor_w, anchor_h = W - broll_win_w, body_h  # 520x514
        max_words_chunk = 11
        hl_max_chars = 66
        desk_ratio = 0.88

    animator = BroadcastAnchorAnimator(anchor_img_path, width=anchor_w, height=anchor_h, desk_ratio=desk_ratio)

    # Pre-render Short Desk Pedestal Footer (y = 1648..1920) so bottom of Short looks like a real TV News Desk
    if is_short:
        ped_h = 272
        ped_img = Image.new("RGB", (W, ped_h), (10, 15, 32))
        p_draw = ImageDraw.Draw(ped_img)
        for py in range(ped_h):
            p_draw.line([(0, py), (W, py)], fill=(int(10 + 14 * (py / ped_h)), int(16 + 18 * (py / ped_h)), int(36 + 35 * (py / ped_h))))
        p_draw.rectangle([0, 0, W, 6], fill=(195, 18, 30))
        p_draw.rounded_rectangle([60, 28, W - 60, ped_h - 36], radius=18, fill=(14, 22, 46), outline=(250, 195, 0), width=3)
        p_draw.rounded_rectangle([90, 52, W - 90, 128], radius=10, fill=(185, 16, 30))
        draw_bilingual_text(p_draw, (215, 68), "24x7 LIVE NEWS NETWORK", size=34, fill=(255, 255, 255))
        sub_ped = "सत्य • सटीक • सबसे पहले  |  HD BROADCAST" if language == "hindi" else "FAST • ACCURATE • VERIFIED  |  HD BROADCAST"
        draw_bilingual_text(p_draw, (195, 152), sub_ped, size=28, fill=(255, 215, 0))
        pedestal_arr = np.asarray(ped_img, dtype=np.uint8)
    else:
        # Pre-render 16:9 Top Studio Header Bar (1280x46)
        hdr_img = Image.new("RGB", (W, header_h), (12, 18, 38))
        h_draw = ImageDraw.Draw(hdr_img)
        h_draw.rectangle([0, header_h - 3, W, header_h], fill=(250, 195, 0))
        h_draw.rounded_rectangle([16, 6, 178, header_h - 8], radius=6, fill=(220, 18, 32))
        h_draw.ellipse([28, 16, 40, 28], fill=(255, 255, 255))
        draw_bilingual_text(h_draw, (48, 9), "LIVE 24x7", size=20, fill=(255, 255, 255))
        h_draw.rounded_rectangle([190, 6, 350, header_h - 8], radius=6, fill=(22, 34, 68), outline=(250, 195, 0), width=2)
        draw_bilingual_text(h_draw, (208, 9), category, size=20, fill=(255, 215, 0))
        hdr_title = "प्राइम टाइम महाबुलेटिन  |  SPECIAL PRIME TIME REPORT" if language == "hindi" else "GLOBAL PRIME TIME SPECIAL REPORT  |  24x7 NEWS DESK"
        draw_bilingual_text(h_draw, (375, 9), hdr_title, size=21, fill=(240, 245, 255))
        header_arr = np.asarray(hdr_img, dtype=np.uint8)

    # Pre-render Top-Left LIVE badge for Short B-roll
    badge_on = Image.new("RGB", (440, 56), (14, 22, 48))
    bo_draw = ImageDraw.Draw(badge_on)
    bo_draw.rectangle([0, 0, 215, 56], fill=(230, 18, 32))
    bo_draw.ellipse([18, 18, 38, 38], fill=(255, 255, 255))
    draw_bilingual_text(bo_draw, (48, 11), "LIVE 24x7", size=26, fill=(255, 255, 255))
    bo_draw.rectangle([215, 0, 440, 56], fill=(14, 22, 48), outline=(255, 200, 0), width=2)
    draw_bilingual_text(bo_draw, (235, 11), category, size=26, fill=(255, 215, 0))
    badge_on_arr = np.asarray(badge_on, dtype=np.uint8)

    prepared_scenes = []
    concat_list_path = "temp/audio_concat.txt"
    total_duration = 0.0
    broll_cache = {}

    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for idx, asset in enumerate(scene_assets):
            dur = _get_audio_duration(asset["audio_path"])
            env = _extract_audio_envelope(asset["audio_path"], dur, fps=fps)
            f_concat.write(f"file '{os.path.abspath(asset['audio_path'])}'\n")

            img_p = asset["image_path"]
            if img_p not in broll_cache:
                broll_pil = Image.open(img_p).convert("RGB").resize(
                    (int(broll_win_w * 1.12), int(broll_win_h * 1.12)), Image.Resampling.BILINEAR
                )
                broll_cache[img_p] = np.asarray(broll_pil, dtype=np.uint8)
            broll_base_arr = broll_cache[img_p]

            headline_banner = asset.get("headline_banner") or script_data.get("headline_banner", "BREAKING NEWS")
            narration = asset.get("subtitles") or asset.get("narration", "")
            caption_chunks = _split_caption_chunks(narration, max_words_per_chunk=max_words_chunk)

            strap_img = Image.new("RGB", (W, strap_h), (155, 12, 24))
            s_draw = ImageDraw.Draw(strap_img)
            s_draw.rectangle([0, 0, W, 5], fill=(255, 205, 0))
            s_draw.rectangle([0, strap_h - 5, W, strap_h], fill=(255, 205, 0))
            badge_label = "बड़ी ख़बर" if language == "hindi" else "BREAKING"
            tag_w = 225 if is_short else 185
            s_draw.polygon([(0, 5), (tag_w, 5), (tag_w - 22, strap_h - 5), (0, strap_h - 5)], fill=(250, 195, 0))
            strap_font_sz = 28 if is_short else 22
            hl_font_sz = 32 if is_short else 24
            ty_strap = (strap_h - strap_font_sz) // 2 - 2
            draw_bilingual_text(s_draw, (18, ty_strap), badge_label, size=strap_font_sz, fill=(15, 15, 20))

            hl_clean = headline_banner.strip()
            if len(hl_clean) > hl_max_chars:
                hl_clean = hl_clean[: hl_max_chars - 2] + "..."
            draw_bilingual_text(s_draw, (tag_w + 12, (strap_h - hl_font_sz) // 2 - 2), hl_clean, size=hl_font_sz, fill=(255, 255, 255))
            strap_rgb = np.asarray(strap_img, dtype=np.uint8)

            sub_cards = []
            sub_font_sz = 31 if is_short else 22
            for chunk in caption_chunks:
                sc_img = Image.new("RGB", (W, sub_h), (10, 14, 28))
                sc_draw = ImageDraw.Draw(sc_img)
                sc_draw.rectangle([0, 0, W, 3], fill=(0, 195, 255))
                sc_draw.rounded_rectangle([18, 7, W - 18, sub_h - 6], radius=10, fill=(18, 24, 46), outline=(255, 205, 0), width=2)
                cy_dot = sub_h // 2
                sc_draw.ellipse([34, cy_dot - 7, 48, cy_dot + 7], fill=(235, 30, 45))
                speaker_tag = "एंकर:" if language == "hindi" else "ANCHOR:"
                draw_bilingual_text(sc_draw, (60, (sub_h - sub_font_sz) // 2 - 2), f"{speaker_tag}  {chunk}", size=sub_font_sz, fill=(255, 248, 210))
                sub_cards.append(np.asarray(sc_img, dtype=np.uint8))

            prepared_scenes.append({
                "idx": idx,
                "dur": dur,
                "start_t": total_duration,
                "env": env,
                "broll_base_arr": broll_base_arr,
                "strap_rgb": strap_rgb,
                "sub_cards": sub_cards,
            })
            total_duration += dur

    merged_voice_wav = "temp/merged_voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-ar", "24000", "-ac", "1", merged_voice_wav],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    bgm_wav = _create_bgm_wav(total_duration + 3.0, "temp/broadcast_bgm.wav")
    final_audio_wav = "temp/final_mixed_audio.wav"
    if bgm_wav and os.path.exists(merged_voice_wav):
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", merged_voice_wav, "-i", bgm_wav,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
                "-map", "[aout]", final_audio_wav,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    else:
        final_audio_wav = merged_voice_wav

    logger.info(f"🎬 Rendering {fps}fps {'SHORT (1080x1920)' if is_short else 'LONG (1280x720 HD)'} Video ({total_duration:.1f}s = {total_duration/60.0:.1f} min) to {output_path}...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "-", "-i", final_audio_wav,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    mv = memoryview(canvas)

    for sc in prepared_scenes:
        n_frames = max(1, int(round(sc["dur"] * fps)))
        idx, dur, env = sc["idx"], sc["dur"], sc["env"]
        broll_base_arr = sc["broll_base_arr"]
        strap_rgb, sub_cards = sc["strap_rgb"], sc["sub_cards"]
        scene_start_t = sc["start_t"]
        bh, bw, _ = broll_base_arr.shape
        max_dx = max(1, bw - broll_win_w)
        max_dy = max(1, bh - broll_win_h)

        for f_i in range(n_frames):
            t = f_i / float(fps)
            gt = scene_start_t + t
            speech_amp = float(env[min(len(env) - 1, f_i)])

            prog = min(1.0, max(0.0, t / max(0.1, dur)))
            if idx % 2 == 0:
                crop_x = int(max_dx * prog * 0.8)
                crop_y = int(max_dy * (1.0 - prog) * 0.7)
            else:
                crop_x = int(max_dx * (1.0 - prog) * 0.8)
                crop_y = int(max_dy * prog * 0.7)

            broll_view = broll_base_arr[crop_y : crop_y + broll_win_h, crop_x : crop_x + broll_win_w]
            anchor_arr = animator.render_frame(gt, speech_amp=speech_amp)
            chunk_idx = min(len(sub_cards) - 1, int((t / max(0.1, dur)) * len(sub_cards)))
            scroll_x = int(gt * 150) % max(1, min(unit_px, ticker_arr.shape[1] - W - 1))

            if is_short:
                # 1. Top B-Roll (y = 0..830) + LIVE Badge
                canvas[0:830, :, :] = broll_view
                canvas[34:90, 32:472, :] = badge_on_arr
                # 2. Center 3D Headline Strap (y = 830..934)
                canvas[830:934, :, :] = strap_rgb
                # 3. Studio Anchor + 3D Broadcast Desk (y = 934..1920)
                canvas[934:1920, :, :] = anchor_arr
                # 4. Audio Waveform Bar + Synced Subtitle Card on Desk (y = 1486..1590)
                bar_w = int(W * (0.18 + 0.72 * speech_amp))
                x_s = (W - bar_w) // 2
                canvas[1486:1494, x_s : x_s + bar_w, :] = (255, 65, 75)
                canvas[1494:1590, :, :] = sub_cards[chunk_idx]
                # 5. Scrolling Yellow News Ticker (y = 1590..1648)
                canvas[1590:1648, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]
                # 6. Illuminated Studio Desk Pedestal Footer (y = 1648..1920) - ZERO BLACK BARS!
                canvas[1648:1920, :, :] = pedestal_arr
            else:
                # 16:9 Horizontal Prime-Time Layout (1280x720)
                canvas[0:46, :, :] = header_arr
                canvas[46:560, 0:760, :] = broll_view
                canvas[46:560, 760:1280, :] = anchor_arr
                canvas[46:560, 756:764, :] = (250, 195, 0)  # Gold center divider
                canvas[560:618, :, :] = strap_rgb
                canvas[618:676, :, :] = sub_cards[chunk_idx]
                canvas[676:720, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]

            try:
                proc.stdin.write(mv)
            except (BrokenPipeError, IOError):
                break

    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.wait(timeout=900)
    logger.info(f"✅ Broadcast Video Rendered: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
    return output_path


# ================= 8. YOUTUBE UPLOAD & 10-MINUTE GUARANTEE ORCHESTRATOR =================
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
    logger.info(f"🎬 Starting Production: {category} | Format: {'SHORT (9:16)' if is_short else 'LONG (16:9 - 10+ MIN)'} | Breaking: {is_breaking}")
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
    raw_headlines = script_data.get("raw_headlines", [])

    logger.info(
        f"📋 Script Ready: '{script_data.get('title')}' | Category: {resolved_cat} | "
        f"Language: {language.upper()} | Anchor: {chosen_gender.upper()} | Initial Scenes: {len(scenes)}"
    )

    anchor_img_path = f"temp/anchor_{chosen_gender}_{resolved_cat.lower()}.jpg"
    download_anchor_studio_image(
        anchor_gender=chosen_gender,
        category=resolved_cat,
        output_path=anchor_img_path,
    )

    # For Long Videos, generate up to 6 unique high-res B-roll images and cycle them across segments for speed
    max_unique_images = 4 if is_short else 6
    broll_paths = []
    for idx in range(min(len(scenes), max_unique_images)):
        sc = scenes[idx]
        img_path = f"temp/scene_broll_{idx + 1}.jpg"
        download_scene_image(
            prompt=sc.get("image_prompt", ""),
            output_path=img_path,
            is_short=is_short,
            search_query=sc.get("search_query", ""),
            rss_image_url=sc.get("rss_image_url", ""),
            headline_text=sc.get("headline_banner", ""),
        )
        broll_paths.append(img_path)

    scene_assets = []
    cumulative_sec = 0.0

    for idx, scene in enumerate(scenes):
        sid = idx + 1
        audio_path = f"temp/voice_{sid}.mp3"
        img_path = broll_paths[idx % len(broll_paths)]

        synthesize_broadcast_voice(
            text=scene.get("narration", ""),
            output_path=audio_path,
            category=resolved_cat,
            gender=chosen_gender,
            language=language,
        )
        dur = _get_audio_duration(audio_path)
        cumulative_sec += dur

        scene_assets.append({
            "scene_id": sid,
            "audio_path": audio_path,
            "image_path": img_path,
            "narration": scene.get("narration", ""),
            "subtitles": scene.get("subtitles", scene.get("narration", "")),
            "headline_banner": scene.get("headline_banner", script_data.get("headline_banner", "BREAKING NEWS")),
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    # HARD 10-MINUTE GUARANTEE FOR LONG VIDEOS ( >= 605 seconds )
    extra_idx = 0
    while (not is_short) and (cumulative_sec < MIN_LONG_VIDEO_SECONDS) and (len(scene_assets) < 32):
        hl = raw_headlines[extra_idx % len(raw_headlines)] if raw_headlines else {"title": script_data.get("headline_banner", "बड़ी ख़बर"), "summary": ""}
        sid = len(scene_assets) + 1
        extra_nar = _build_detailed_story_narration(sid, sid + 2, hl, language=language, is_short=False)
        audio_path = f"temp/voice_{sid}.mp3"
        synthesize_broadcast_voice(
            text=extra_nar,
            output_path=audio_path,
            category=resolved_cat,
            gender=chosen_gender,
            language=language,
        )
        dur = _get_audio_duration(audio_path)
        cumulative_sec += dur
        scene_assets.append({
            "scene_id": sid,
            "audio_path": audio_path,
            "image_path": broll_paths[extra_idx % len(broll_paths)],
            "narration": extra_nar,
            "subtitles": extra_nar,
            "headline_banner": hl.get("title", script_data.get("headline_banner", "बड़ी ख़बर"))[:68],
            "camera_angle": "closeup" if sid % 2 == 1 else "wide",
        })
        extra_idx += 1
        logger.info(f"➕ Extended Long Bulletin to {cumulative_sec:.1f}s / {MIN_LONG_VIDEO_SECONDS:.0f}s (Scene #{sid})")

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

    logger.info(f"🎉 Broadcast Video Ready: {output_video} (Total Duration: {cumulative_sec/60.0:.2f} minutes)")
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
        help="Video format: 'short' (9:16), 'long' (16:9, 10+ min), or 'both'",
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
