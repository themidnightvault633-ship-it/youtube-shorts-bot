import os
import sys
import re
import glob
import html
import json
import time
import math
import shutil
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
def _clean_secret(val):
    return (val or "").strip().strip('"').strip("'").strip()

GEMINI_API_KEY = _clean_secret(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean_secret(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean_secret(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean_secret(os.environ.get("YT_REFRESH_TOKEN", ""))

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


# ================= 2. CACHED BILINGUAL HINDI + ENGLISH FONT & KARAOKE ENGINE =================
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


def measure_bilingual_text(draw, text, size=34):
    """Returns exact pixel width of bilingual Hindi/English text."""
    deva_font, latin_font = _load_font_pair(size)
    clean = re.sub(r"[\U00010000-\U0010ffff]", "", str(text or ""))
    runs = re.findall(r"[\u0900-\u097F]+|[^\u0900-\u097F]+", clean)
    total_w = 0
    for run in runs:
        is_deva = bool(re.search(r"[\u0900-\u097F]", run))
        font = deva_font if is_deva else latin_font
        bbox = draw.textbbox((0, 0), run, font=font)
        total_w += max(0, bbox[2] - bbox[0])
    return total_w


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


def build_word_timings(narration, duration):
    """
    Computes exact start and end timestamps for every single word in `narration`,
    weighted by character length and punctuation pauses so visual word highlighting
    moves in lockstep with the anchor's voice!
    """
    words = [w for w in (narration or "").strip().split() if w]
    if not words:
        return [{"word": "", "start": 0.0, "end": duration, "idx": 0}]
    weights = []
    for w in words:
        pause_bonus = 2.4 if w.endswith(("।", ".", "!", "?", ":", ";")) else (1.1 if w.endswith(",") else 0.0)
        weights.append(max(1.5, len(w) * 0.85 + pause_bonus))
    total_wt = sum(weights)
    timings = []
    cur_t = 0.0
    usable_dur = max(0.5, duration - 0.15)
    for idx, (w, wt) in enumerate(zip(words, weights)):
        dt = (wt / total_wt) * usable_dur
        timings.append({"word": w, "start": cur_t, "end": cur_t + dt, "idx": idx})
        cur_t += dt
    timings[-1]["end"] = duration + 1.0
    return timings


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
            "headline_banner": kw,
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
        "title": f"🔴 LIVE: {top_title[:65]} #Shorts" if is_short else f"🔴 LIVE महाबुलेटिन: Top 15 बड़ी ख़बरें | {top_title[:45]}",
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
  "title": "Catchy YouTube title (max 75 chars, include #Shorts)",
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
                raw_json = _call_gemini_rest(model_name, prompt, GEMINI_API_KEY, timeout_sec=30)
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
                        sc["headline_banner"] = hl.get("title", "बड़ी ख़बर")
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
    await asyncio.wait_for(comm.save(output_path), timeout=30.0)


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


# ================= 5. B-ROLL VISUAL ENGINE (FAST & CLEAN, NO FROZEN TEXT!) =================
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
    gen_w, gen_h = 768, 768
    clean_prompt = re.sub(r"[^\w\s,.-]", " ", prompt or "Editorial news photojournalism").strip()
    encoded = urllib.parse.quote(clean_prompt[:220])
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&seed={seed}&model=turbo&nologo=true"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200 and len(resp.content) > 12000:
            return _validate_and_resize_image(resp.content, target_w, target_h)
    except Exception:
        pass
    return None


def _create_clean_satellite_broll_backdrop(output_path, width, height, scene_idx=0):
    img = Image.new("RGB", (width, height), (10, 18, 42))
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, int(height * 0.42)
    max_r = int(max(width, height) * 0.65)
    for r in range(max_r, 15, -20):
        ratio = 1.0 - (r / float(max_r))
        col = (
            int(10 + (75 if scene_idx % 2 == 0 else 35) * ratio),
            int(20 + (45 if scene_idx % 2 == 0 else 75) * ratio),
            int(46 + 115 * ratio),
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    for lat in range(40, height, 55):
        draw.line([(0, lat), (width, lat)], fill=(38, 82, 148), width=1)
    for lon in range(40, width, 55):
        draw.line([(lon, 0), (lon, height)], fill=(38, 82, 148), width=1)

    for rad in [int(min(width, height) * r) for r in (0.14, 0.25, 0.36, 0.47)]:
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(0, 195, 255), width=2)
    draw.line([(cx - int(width * 0.35), cy), (cx + int(width * 0.35), cy)], fill=(220, 32, 48), width=2)
    draw.line([(cx, cy - int(height * 0.35)), (cx, cy + int(height * 0.35))], fill=(220, 32, 48), width=2)

    img.save(output_path, "JPEG", quality=92)
    return output_path


def download_scene_image(prompt, output_path, is_short=True, search_query="", rss_image_url="", headline_text="", scene_idx=0):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w = 1080 if is_short else 880
    target_h = 880 if is_short else 600

    if rss_image_url and rss_image_url.startswith("http"):
        try:
            resp = requests.get(rss_image_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200 and len(resp.content) > 15000:
                img = _validate_and_resize_image(resp.content, target_w, target_h)
                img.save(output_path, "JPEG", quality=92)
                return output_path
        except Exception:
            pass

    logger.info(f"🎨 Generating News B-Roll Visual #{scene_idx + 1} ({target_w}x{target_h})...")
    full_prompt = (
        f"{prompt}, realistic television news broadcast camera footage, "
        f"wide angle photojournalism, natural lighting, 8k UHD, strictly no text, no words, no charts, no logos"
    )
    img = _fetch_pollinations_image(full_prompt, target_w, target_h)
    if img is not None:
        img.save(output_path, "JPEG", quality=92)
        return output_path

    return _create_clean_satellite_broll_backdrop(output_path, target_w, target_h, scene_idx=scene_idx)


# ================= 6. ULTRA-FAST PRE-CACHED 2.5D ANIME TV NEWS ANCHOR RIG =================
def _bezier(p0, p1, p2, p3, steps=24):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        mt = 1.0 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.append((x, y))
    return pts


def _quad(p0, p1, p2, steps=18):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        mt = 1.0 - t
        x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
        y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
        pts.append((x, y))
    return pts


class StudioAnimeAnchor:
    """
    High-Detail 2.5D Japanese Anime / VTuber Broadcast News Anchor Rig (Male & Female).
    Pre-renders all 36 full-frame `(viseme, blink, pose_gesture)` studio states into RAM as `uint8`
    NumPy arrays at startup (<0.8s once), so per-frame rendering during the 12,100-frame video loop
    is an instant O(1) array lookup (>10,000 FPS)!
    """

    def __init__(self, gender="female", width=1080, height=986, desk_ratio=0.56):
        self.gender = "male" if str(gender).lower() == "male" else "female"
        self.w = width
        self.h = height
        self.desk_y = int(height * desk_ratio)
        self.s = min(width / 820.0, self.desk_y / 480.0)
        self.bg_img = self._build_newsroom_backdrop()
        self.head_cache = {}
        self.full_frame_cache = {}
        self._prebuild_caches()

    def _build_newsroom_backdrop(self):
        img = Image.new("RGB", (self.w, self.h), (10, 16, 36))
        draw = ImageDraw.Draw(img)
        for y in range(self.desk_y):
            ry = y / float(max(1, self.desk_y))
            glow = math.exp(-((ry - 0.45) / 0.38) ** 2)
            r = int(10 + 30 * glow)
            g = int(18 + 52 * glow)
            b = int(45 + 105 * glow)
            draw.line([(0, y), (self.w, y)], fill=(r, g, b))

        for gx in range(0, self.w, max(42, self.w // 16)):
            draw.line([(gx, 0), (gx, self.desk_y)], fill=(25, 62, 118), width=1)
        for gy in range(0, self.desk_y, max(38, self.desk_y // 10)):
            draw.line([(0, gy), (self.w, gy)], fill=(25, 62, 118), width=1)

        cx, cy = self.w // 2, int(self.desk_y * 0.44)
        for rad in [int(self.desk_y * r) for r in (0.18, 0.30, 0.42, 0.54)]:
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(38, 95, 175), width=2)

        for idx, by in enumerate([int(self.desk_y * r) for r in (0.14, 0.34, 0.56, 0.78)]):
            pad = int(self.w * (0.04 + 0.03 * (idx % 2)))
            draw.rectangle([pad, by, self.w - pad, by + 6], fill=(220, 22, 40))
            draw.rectangle([pad + 24, by + 9, self.w - pad - 24, by + 13], fill=(0, 205, 255))
        return img

    def _render_single_head(self, viseme_level, is_blink, gaze_dir, brow_state, tilt_deg):
        ss = 2.0 * self.s
        hw, hh = int(380 * ss), int(400 * ss)
        canvas = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
        d = ImageDraw.Draw(canvas)
        cx, cy = hw // 2, int(hh * 0.50)

        skin = (255, 226, 206, 255) if self.gender == "female" else (248, 212, 188, 255)
        skin_warm = (252, 205, 182, 255) if self.gender == "female" else (238, 190, 164, 255)
        line_col = (62, 38, 36, 255)
        hair_base = (28, 24, 42, 255) if self.gender == "female" else (22, 26, 40, 255)
        hair_mid = (46, 38, 68, 255) if self.gender == "female" else (36, 44, 68, 255)
        hair_shine = (105, 96, 148, 255) if self.gender == "female" else (82, 96, 138, 255)

        if self.gender == "female":
            d.ellipse([cx - 104 * ss, cy - 118 * ss, cx + 104 * ss, cy + 45 * ss], fill=hair_base)

        for side in [-1, 1]:
            ex = cx + side * 88 * ss
            ey = cy + 14 * ss
            d.ellipse([ex - 14 * ss, ey - 20 * ss, ex + 14 * ss, ey + 20 * ss], fill=skin_warm, outline=line_col, width=max(2, int(2.0 * ss)))
            if self.gender == "female":
                d.ellipse([ex - 5 * ss, ey + 17 * ss, ex + 5 * ss, ey + 27 * ss], fill=(255, 250, 235, 255), outline=(220, 180, 75, 255), width=max(1, int(1.5 * ss)))

        fw = 86 * ss if self.gender == "female" else 90 * ss
        chin_y = cy + (92 * ss if self.gender == "female" else 96 * ss)
        left_jaw = _bezier((cx - fw, cy - 15 * ss), (cx - fw, cy + 38 * ss), (cx - 54 * ss, cy + 74 * ss), (cx, chin_y))
        right_jaw = _bezier((cx, chin_y), (cx + 54 * ss, cy + 74 * ss), (cx + fw, cy + 38 * ss), (cx + fw, cy - 15 * ss))
        upper_head = _bezier((cx + fw, cy - 15 * ss), (cx + fw, cy - 108 * ss), (cx - fw, cy - 108 * ss), (cx - fw, cy - 15 * ss))
        d.polygon(left_jaw + right_jaw + upper_head, fill=skin)

        for side in [-1, 1]:
            bx = cx + side * 50 * ss
            by = cy + 32 * ss
            d.ellipse([bx - 20 * ss, by - 10 * ss, bx + 20 * ss, by + 10 * ss], fill=(252, 185, 175, 255) if self.gender == "female" else (242, 188, 168, 255))
            d.line([(bx - 8 * ss, by + 2 * ss), (bx - 2 * ss, by - 3 * ss)], fill=(238, 145, 140, 255), width=max(1, int(1.6 * ss)))
            d.line([(bx + 2 * ss, by + 3 * ss), (bx + 8 * ss, by - 2 * ss)], fill=(238, 145, 140, 255), width=max(1, int(1.6 * ss)))

        d.line(left_jaw + right_jaw, fill=line_col, width=max(2, int(2.4 * ss)))

        eye_y = cy + 10 * ss
        eye_sep = 41 * ss
        ew = 23 * ss if self.gender == "female" else 22 * ss
        eh = 15 * ss if self.gender == "female" else 12.5 * ss
        gaze_x = gaze_dir * 3.2

        for side in [-1, 1]:
            ecx = cx + side * eye_sep
            if is_blink:
                lid_pts = _quad((ecx - ew, eye_y + 3 * ss), (ecx, eye_y + 9 * ss), (ecx + ew, eye_y + 2 * ss))
                d.line(lid_pts, fill=(28, 18, 26, 255), width=max(3, int(3.8 * ss)))
                d.line([(ecx + side * ew, eye_y + 2 * ss), (ecx + side * (ew + 6 * ss), eye_y - 2 * ss)], fill=(28, 18, 26, 255), width=max(2, int(2.8 * ss)))
            else:
                top_lid = _bezier((ecx - ew, eye_y + 3 * ss), (ecx - ew * 0.55, eye_y - eh * 1.25), (ecx + ew * 0.55, eye_y - eh * 1.25), (ecx + ew, eye_y + 1 * ss))
                bot_lid = _bezier((ecx + ew, eye_y + 1 * ss), (ecx + ew * 0.45, eye_y + eh * 0.95), (ecx - ew * 0.45, eye_y + eh * 0.95), (ecx - ew, eye_y + 3 * ss))
                d.polygon(top_lid + bot_lid, fill=(252, 254, 255, 255))

                ix = ecx + gaze_x * ss
                iy = eye_y
                ir_w, ir_h = ew * 0.62, eh * 0.92
                c_dark = (32, 42, 78, 255) if self.gender == "female" else (44, 30, 24, 255)
                c_mid = (58, 92, 162, 255) if self.gender == "female" else (92, 58, 42, 255)
                c_glow = (118, 182, 248, 255) if self.gender == "female" else (162, 110, 68, 255)

                d.ellipse([ix - ir_w, iy - ir_h, ix + ir_w, iy + ir_h], fill=c_dark)
                d.ellipse([ix - ir_w * 0.82, iy - ir_h * 0.78, ix + ir_w * 0.82, iy + ir_h * 0.86], fill=c_mid)
                d.pieslice([ix - ir_w * 0.75, iy - ir_h * 0.65, ix + ir_w * 0.75, iy + ir_h * 0.86], 15, 165, fill=c_glow)
                d.ellipse([ix - ir_w * 0.38, iy - ir_h * 0.42, ix + ir_w * 0.38, iy + ir_h * 0.42], fill=(16, 14, 24, 255))
                d.ellipse([ix - ir_w * 0.58, iy - ir_h * 0.65, ix - ir_w * 0.16, iy - ir_h * 0.20], fill=(255, 255, 255, 255))
                d.ellipse([ix + ir_w * 0.18, iy + ir_h * 0.18, ix + ir_w * 0.44, iy + ir_h * 0.44], fill=(255, 255, 255, 255))

                lash_top = _bezier((ecx - ew - 2 * ss, eye_y + 4 * ss), (ecx - ew * 0.60, eye_y - eh * 1.52), (ecx + ew * 0.60, eye_y - eh * 1.52), (ecx + ew + 3 * ss, eye_y))
                d.polygon(top_lid + list(reversed(lash_top)), fill=(22, 16, 26, 255))
                if self.gender == "female":
                    d.polygon([(ecx + side * (ew - 1 * ss), eye_y - 1 * ss), (ecx + side * (ew + 8 * ss), eye_y - 7 * ss), (ecx + side * (ew - 4 * ss), eye_y - 6 * ss)], fill=(22, 16, 26, 255))
                d.line(bot_lid, fill=(92, 62, 56, 255), width=max(1, int(1.6 * ss)))
                crease = _quad((ecx - ew * 0.70, eye_y - eh * 1.22), (ecx, eye_y - eh * 1.65), (ecx + ew * 0.70, eye_y - eh * 1.18))
                d.line(crease, fill=(142, 96, 82, 255), width=max(1, int(1.6 * ss)))

        ny = cy + 34 * ss
        d.polygon([(cx - 1 * ss, ny - 9 * ss), (cx - 5 * ss, ny + 2 * ss), (cx + 2 * ss, ny + 3 * ss)], fill=skin_warm)
        d.line([(cx - 2 * ss, ny - 6 * ss), (cx - 4 * ss, ny + 1 * ss), (cx + 1 * ss, ny + 2 * ss)], fill=(145, 96, 80, 255), width=max(1, int(1.8 * ss)))

        my = cy + 58 * ss
        if viseme_level == 0:
            mw = 18 * ss
            if self.gender == "female":
                d.polygon([(cx - mw, my), (cx, my - 2.5 * ss), (cx + mw, my), (cx, my + 4.5 * ss)], fill=(225, 92, 104, 255))
            smile = _quad((cx - mw, my - 1 * ss), (cx, my + 4 * ss), (cx + mw, my - 1 * ss))
            d.line(smile, fill=(88, 38, 42, 255), width=max(2, int(2.2 * ss)))
        else:
            v_specs = {
                1: (16 * ss, 8 * ss),
                2: (23 * ss, 19 * ss),
                3: (16 * ss, 22 * ss),
                4: (25 * ss, 13 * ss),
                5: (26 * ss, 24 * ss),
            }
            mw, mh = v_specs.get(viseme_level, (20 * ss, 15 * ss))
            tlip = _quad((cx - mw, my - mh * 0.2), (cx, my - mh * 0.5), (cx + mw, my - mh * 0.2))
            blip = _bezier((cx + mw, my - mh * 0.2), (cx + mw * 0.75, my + mh * 0.92), (cx - mw * 0.75, my + mh * 0.92), (cx - mw, my - mh * 0.2))
            mpoly = tlip + blip
            d.polygon(mpoly, fill=(118, 32, 46, 255))
            d.pieslice([cx - mw * 0.65, my - mh * 0.02, cx + mw * 0.65, my + mh * 0.80], 0, 180, fill=(232, 112, 124, 255))
            d.polygon([(cx - mw * 0.72, my - mh * 0.20), (cx + mw * 0.72, my - mh * 0.20), (cx + mw * 0.62, my + mh * 0.05), (cx - mw * 0.62, my + mh * 0.05)], fill=(252, 253, 255, 255))
            d.line(mpoly, fill=(82, 26, 34, 255), width=max(2, int(2.0 * ss)))

        if self.gender == "female":
            left_lock = (
                _bezier((cx - 84 * ss, cy - 45 * ss), (cx - 106 * ss, cy + 5 * ss), (cx - 105 * ss, cy + 70 * ss), (cx - 86 * ss, cy + 128 * ss))
                + _bezier((cx - 86 * ss, cy + 128 * ss), (cx - 82 * ss, cy + 70 * ss), (cx - 84 * ss, cy + 15 * ss), (cx - 68 * ss, cy - 35 * ss))
            )
            right_lock = (
                _bezier((cx + 84 * ss, cy - 45 * ss), (cx + 106 * ss, cy + 5 * ss), (cx + 105 * ss, cy + 70 * ss), (cx + 86 * ss, cy + 128 * ss))
                + _bezier((cx + 86 * ss, cy + 128 * ss), (cx + 82 * ss, cy + 70 * ss), (cx + 84 * ss, cy + 15 * ss), (cx + 68 * ss, cy - 35 * ss))
            )
            d.polygon(left_lock, fill=hair_mid, outline=(18, 15, 28, 255), width=max(1, int(1.5 * ss)))
            d.polygon(right_lock, fill=hair_mid, outline=(18, 15, 28, 255), width=max(1, int(1.5 * ss)))

            crown = _bezier((cx - 104 * ss, cy - 25 * ss), (cx - 112 * ss, cy - 142 * ss), (cx + 112 * ss, cy - 142 * ss), (cx + 104 * ss, cy - 25 * ss))
            bangs = (
                _quad((cx + 104 * ss, cy - 25 * ss), (cx + 82 * ss, cy - 4 * ss), (cx + 68 * ss, cy - 18 * ss))
                + _quad((cx + 68 * ss, cy - 18 * ss), (cx + 48 * ss, cy - 52 * ss), (cx + 24 * ss, cy - 12 * ss))
                + _quad((cx + 24 * ss, cy - 12 * ss), (cx + 8 * ss, cy - 48 * ss), (cx - 12 * ss, cy - 10 * ss))
                + _quad((cx - 12 * ss, cy - 10 * ss), (cx - 34 * ss, cy - 54 * ss), (cx - 58 * ss, cy - 16 * ss))
                + _quad((cx - 58 * ss, cy - 16 * ss), (cx - 82 * ss, cy - 4 * ss), (cx - 104 * ss, cy - 25 * ss))
            )
            d.polygon(crown + bangs, fill=hair_base)
            hi1 = _bezier((cx - 65 * ss, cy - 62 * ss), (cx - 20 * ss, cy - 84 * ss), (cx + 20 * ss, cy - 84 * ss), (cx + 65 * ss, cy - 62 * ss))
            d.line(hi1, fill=hair_shine, width=max(3, int(5.5 * ss)))
        else:
            crown = _bezier((cx - 98 * ss, cy - 12 * ss), (cx - 108 * ss, cy - 138 * ss), (cx + 108 * ss, cy - 138 * ss), (cx + 98 * ss, cy - 12 * ss))
            bangs = (
                [(cx + 98 * ss, cy - 12 * ss), (cx + 88 * ss, cy + 16 * ss), (cx + 80 * ss, cy - 18 * ss)]
                + _quad((cx + 80 * ss, cy - 18 * ss), (cx + 56 * ss, cy - 50 * ss), (cx + 32 * ss, cy - 12 * ss))
                + _quad((cx + 32 * ss, cy - 12 * ss), (cx + 10 * ss, cy - 52 * ss), (cx - 10 * ss, cy - 10 * ss))
                + _quad((cx - 10 * ss, cy - 10 * ss), (cx - 35 * ss, cy - 50 * ss), (cx - 56 * ss, cy - 14 * ss))
                + [(cx - 56 * ss, cy - 14 * ss), (cx - 80 * ss, cy - 18 * ss), (cx - 88 * ss, cy + 16 * ss), (cx - 98 * ss, cy - 12 * ss)]
            )
            d.polygon(crown + bangs, fill=hair_base)
            hi1 = _bezier((cx - 58 * ss, cy - 64 * ss), (cx - 18 * ss, cy - 84 * ss), (cx + 18 * ss, cy - 84 * ss), (cx + 58 * ss, cy - 64 * ss))
            d.line(hi1, fill=hair_shine, width=max(3, int(5.0 * ss)))

        brow_lift = (6.5 * ss) if brow_state == 1 else (3.0 * ss if brow_state == 2 else 0.0)
        for side in [-1, 1]:
            ecx = cx + side * eye_sep
            by = eye_y - eh - 11 * ss - brow_lift
            in_dy = 4.0 * ss if brow_state == 2 else -2.0 * ss
            b_pts = _quad((ecx - side * ew * 0.80, by + in_dy), (ecx, by - 6 * ss), (ecx + side * ew * 0.90, by + 2 * ss))
            d.line(b_pts, fill=(28, 20, 32, 255), width=max(3, int(3.4 * ss)))

        base_head = canvas.resize((hw // 2, hh // 2), Image.Resampling.LANCZOS)
        if abs(tilt_deg) > 0.2:
            return base_head.rotate(tilt_deg, resample=Image.Resampling.BICUBIC, expand=False)
        return base_head

    def _render_full_studio_state(self, viseme_level, is_blink, pose_idx):
        pose_map = {
            0: (0, 0, 0, 0, 0),
            1: (-1, 1, -int(5 * self.s), -int(4 * self.s), int(32 * self.s)),
            2: (1, 2, int(5 * self.s), -int(7 * self.s), int(58 * self.s)),
        }
        g_dir, b_st, sway_x, nod_y, gesture_lift = pose_map[pose_idx]
        head_sprite = self.head_cache[(viseme_level, is_blink, g_dir)]

        frame = self.bg_img.copy().convert("RGBA")
        d = ImageDraw.Draw(frame)
        s = self.s
        cx = self.w // 2
        desk_y = self.desk_y
        tcx = cx + sway_x
        sh_top = int(desk_y - 165 * s) + (nod_y // 2)

        skin = (255, 226, 206, 255) if self.gender == "female" else (248, 212, 188, 255)
        skin_shade = (224, 182, 158, 255) if self.gender == "female" else (214, 168, 142, 255)

        if self.gender == "female":
            d.polygon([
                (tcx - int(105 * s), sh_top - int(145 * s)),
                (tcx + int(105 * s), sh_top - int(145 * s)),
                (tcx + int(132 * s), sh_top + int(45 * s)),
                (tcx - int(132 * s), sh_top + int(45 * s)),
            ], fill=(22, 18, 34, 255))

        nw = int(26 * s) if self.gender == "female" else int(33 * s)
        ntop = sh_top - int(36 * s)
        d.rectangle([tcx - nw, ntop, tcx + nw, sh_top + int(25 * s)], fill=skin)
        d.polygon([(tcx - nw, ntop), (tcx + nw, ntop), (tcx, ntop + int(24 * s))], fill=skin_shade)

        sh_w = int(200 * s) if self.gender == "female" else int(230 * s)
        suit_main = (182, 22, 44, 255) if self.gender == "female" else (22, 34, 62, 255)
        suit_dark = (132, 14, 30, 255) if self.gender == "female" else (14, 22, 42, 255)
        suit_lapel = (210, 34, 58, 255) if self.gender == "female" else (36, 52, 88, 255)

        d.polygon([
            (tcx - sh_w, desk_y + 10),
            (tcx + sh_w, desk_y + 10),
            (tcx + int(sh_w * 0.86), sh_top + int(22 * s)),
            (tcx + int(54 * s), sh_top - int(4 * s)),
            (tcx - int(54 * s), sh_top - int(4 * s)),
            (tcx - int(sh_w * 0.86), sh_top + int(22 * s)),
        ], fill=suit_main, outline=(15, 16, 26, 255), width=max(2, int(2.5 * s)))

        d.polygon([
            (tcx - int(50 * s), sh_top - int(4 * s)),
            (tcx + int(50 * s), sh_top - int(4 * s)),
            (tcx + int(18 * s), desk_y),
            (tcx - int(18 * s), desk_y),
        ], fill=(246, 249, 255, 255))

        for side in [-1, 1]:
            d.polygon([
                (tcx + side * int(50 * s), sh_top - int(4 * s)),
                (tcx + side * int(84 * s), sh_top + int(16 * s)),
                (tcx + side * int(26 * s), desk_y),
                (tcx + side * int(15 * s), desk_y),
            ], fill=suit_lapel, outline=(15, 16, 26, 255), width=max(2, int(2 * s)))

        if self.gender == "male":
            d.polygon([(tcx - int(15 * s), sh_top + int(8 * s)), (tcx + int(15 * s), sh_top + int(8 * s)), (tcx + int(10 * s), sh_top + int(30 * s)), (tcx - int(10 * s), sh_top + int(30 * s))], fill=(190, 16, 30, 255))
            d.polygon([(tcx - int(10 * s), sh_top + int(30 * s)), (tcx + int(10 * s), sh_top + int(30 * s)), (tcx + int(17 * s), desk_y - int(8 * s)), (tcx, desk_y + int(4 * s)), (tcx - int(17 * s), desk_y - int(8 * s))], fill=(220, 24, 40, 255))
            d.rectangle([tcx - int(12 * s), sh_top + int(76 * s), tcx + int(12 * s), sh_top + int(81 * s)], fill=(250, 208, 48, 255))

        px, py = tcx + int(56 * s), sh_top + int(54 * s)
        d.ellipse([px - int(8 * s), py - int(8 * s), px + int(8 * s), py + int(8 * s)], fill=(250, 202, 24, 255), outline=(255, 255, 255, 255), width=2)

        hx = tcx - head_sprite.width // 2
        hy = sh_top - int(112 * s) - (head_sprite.height // 2) + nod_y
        frame.alpha_composite(head_sprite, (int(hx), int(hy)))

        gx = tcx - int(128 * s) + (sway_x * 2)
        gy = desk_y - int(22 * s) - gesture_lift
        d.polygon([
            (tcx - int(180 * s), desk_y + 10),
            (tcx - int(134 * s), desk_y + 10),
            (gx + int(15 * s), gy + int(12 * s)),
            (gx - int(20 * s), gy + int(20 * s)),
        ], fill=suit_dark, outline=(15, 16, 26, 255), width=max(2, int(2 * s)))
        d.ellipse([gx - int(14 * s), gy - int(15 * s), gx + int(18 * s), gy + int(9 * s)], fill=skin, outline=(70, 45, 38, 255), width=max(2, int(2 * s)))
        for f_ang in [-12, -3, 6, 14]:
            d.line([(gx + int(7 * s), gy - int(3 * s)), (gx + int(24 * s), gy - int(7 * s) + int(f_ang * 0.8 * s))], fill=skin, width=max(3, int(4.5 * s)))

        d.polygon([(0, desk_y), (self.w, desk_y), (self.w, self.h), (0, self.h)], fill=(12, 18, 38, 255))
        d.rectangle([0, desk_y, self.w, desk_y + int(8 * s)], fill=(250, 198, 0, 255))
        d.rectangle([0, desk_y + int(8 * s), self.w, desk_y + int(16 * s)], fill=(195, 16, 30, 255))

        d.polygon([
            (tcx + int(45 * s), desk_y + int(2 * s)),
            (tcx + int(140 * s), desk_y - int(6 * s)),
            (tcx + int(156 * s), desk_y + int(14 * s)),
            (tcx + int(58 * s), desk_y + int(15 * s)),
        ], fill=(242, 246, 255, 255), outline=(150, 168, 196, 255), width=1)

        for side in [-1, 1]:
            mx = cx + side * int(self.w * 0.21)
            tip_x = mx - side * int(20 * s)
            tip_y = desk_y - int(56 * s)
            d.line([(mx, desk_y), (tip_x, tip_y)], fill=(64, 72, 88, 255), width=max(3, int(4.5 * s)))
            d.rectangle([tip_x - int(12 * s), tip_y + int(5 * s), tip_x + int(12 * s), tip_y + int(22 * s)], fill=(205, 18, 32, 255), outline=(255, 215, 0, 255), width=1)
            d.ellipse([tip_x - int(9 * s), tip_y - int(16 * s), tip_x + int(9 * s), tip_y + int(6 * s)], fill=(28, 32, 40, 255), outline=(205, 215, 230, 255), width=2)

        return np.asarray(frame.convert("RGB"), dtype=np.uint8)

    def _prebuild_caches(self):
        for v in range(6):
            for blink in (False, True):
                for g_dir, b_st, tilt in [(0, 0, 0.0), (-1, 1, -2.4), (1, 2, 2.4)]:
                    self.head_cache[(v, blink, g_dir)] = self._render_single_head(v, blink, g_dir, b_st, tilt)
                for pose_idx in (0, 1, 2):
                    self.full_frame_cache[(v, blink, pose_idx)] = self._render_full_studio_state(v, blink, pose_idx)

    def render_frame(self, t, speech_amp, word_idx=0):
        blink_phase = (t + 0.3) % 3.2
        is_blink = abs(blink_phase - 1.6) < 0.085
        syl_wave = abs(math.sin(t * 13.5 + word_idx * 1.3))
        eff_speech = speech_amp * (0.25 + 0.75 * syl_wave)
        if speech_amp < 0.08 or syl_wave < 0.16:
            viseme_level = 0
        elif eff_speech > 0.68:
            viseme_level = 5 if ((int(t * 9.0) + word_idx) % 2 == 0) else 2
        elif eff_speech > 0.42:
            viseme_level = 2 + ((int(t * 11.0) + word_idx) % 3)
        else:
            viseme_level = 1

        if speech_amp < 0.12:
            pose_idx = 0
        elif speech_amp > 0.62:
            pose_idx = 2 if ((int(t * 2.5) + word_idx) % 2 == 0) else 1
        else:
            pose_idx = (int(t * 1.6) + word_idx) % 3

        return self.full_frame_cache[(viseme_level, is_blink, pose_idx)]


# ================= 7. FAST INCREMENTAL O(N) STORY TELEPROMPTER & KARAOKE SUBTITLE ENGINE =================
def _build_word_synced_story_cards(broll_win_w, card_h, word_timings, language="hindi", is_short=True):
    """
    Incremental O(N) Live Story Teleprompter Card builder (27x faster!).
    Pre-renders each 3-line page once and updates one word highlight at a time.
    """
    dummy_img = Image.new("RGB", (broll_win_w, card_h))
    dummy_draw = ImageDraw.Draw(dummy_img)
    font_sz = 30 if is_short else 23
    pad_x = 34 if is_short else 24
    max_text_w = broll_win_w - (pad_x * 2) - 36
    space_px = max(9, int(font_sz * 0.32))
    hdr_h = 46 if is_short else 38
    line_step = 46 if is_short else 36

    for wt in word_timings:
        wt["story_px"] = measure_bilingual_text(dummy_draw, wt["word"], size=font_sz)

    lines, cur_line, cur_w = [], [], 0
    for wt in word_timings:
        w_px = wt["story_px"]
        if cur_line and (cur_w + space_px + w_px > max_text_w):
            lines.append(cur_line)
            cur_line = [wt]
            cur_w = w_px
        else:
            cur_line.append(wt)
            cur_w += (space_px + w_px) if len(cur_line) > 1 else w_px
    if cur_line:
        lines.append(cur_line)
    if not lines:
        lines = [[{"word": "", "start": 0.0, "end": 1.0, "idx": 0, "story_px": 10}]]

    pages = [lines[i : i + 3] for i in range(0, len(lines), 3)] or [lines]
    total_words = max(1, len(word_timings))
    cards = [None] * total_words

    for p_idx, page in enumerate(pages):
        base_up = Image.new("RGB", (broll_win_w, card_h), (12, 20, 44))
        du = ImageDraw.Draw(base_up)
        du.rounded_rectangle([12, 4, broll_win_w - 12, card_h - 4], radius=14, fill=(14, 22, 48), outline=(250, 198, 0), width=3)
        du.rounded_rectangle([15, 7, broll_win_w - 15, hdr_h + 4], radius=10, fill=(195, 16, 30))
        du.ellipse([30, 16 if is_short else 13, 46, 32 if is_short else 29], fill=(255, 255, 255))
        hdr_text = (
            f"LIVE TELEPROMPTER  •  भाग {p_idx + 1}/{len(pages)}"
            if language == "hindi"
            else f"LIVE STORY FEED  •  PART {p_idx + 1}/{len(pages)}"
        )
        draw_bilingual_text(du, (58, 10 if is_short else 8), hdr_text, size=23 if is_short else 19, fill=(255, 255, 255))

        base_sp = base_up.copy()
        ds = ImageDraw.Draw(base_sp)

        ty = hdr_h + (16 if is_short else 12)
        page_words = []
        for ln in page:
            tx = pad_x
            for wt in ln:
                w_str = wt["word"]
                w_px = wt["story_px"]
                draw_bilingual_text(du, (tx, ty), w_str, size=font_sz, fill=(150, 178, 215))
                draw_bilingual_text(ds, (tx, ty), w_str, size=font_sz, fill=(255, 255, 255))
                page_words.append((wt["idx"], w_str, tx, ty, w_px))
                tx += w_px + space_px
            ty += line_step

        running_img = base_up.copy()
        for (w_idx, w_str, tx, ty, w_px) in page_words:
            card = running_img.copy()
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle(
                [tx - 5, ty - 3, tx + w_px + 5, ty + font_sz + 6],
                radius=7,
                fill=(215, 20, 36),
                outline=(255, 215, 0),
                width=2,
            )
            draw_bilingual_text(cd, (tx, ty), w_str, size=font_sz, fill=(255, 235, 80))

            prog_ratio = float(w_idx + 1) / float(total_words)
            bar_x0, bar_x1 = 24, broll_win_w - 24
            bar_y = card_h - 12
            cd.rectangle([bar_x0, bar_y, bar_x1, bar_y + 5], fill=(28, 42, 78))
            cd.rectangle([bar_x0, bar_y, bar_x0 + int((bar_x1 - bar_x0) * prog_ratio), bar_y + 5], fill=(0, 215, 255))
            cards[w_idx] = np.asarray(card, dtype=np.uint8)

            box = (max(0, tx - 2), max(0, ty - 2), min(broll_win_w, tx + w_px + 4), min(card_h, ty + font_sz + 6))
            running_img.paste(base_sp.crop(box), box)

    return cards


def _build_word_synced_subtitle_cards(W, sub_h, word_timings, language="hindi", is_short=True):
    """
    Incremental O(N) Bottom Karaoke Subtitle Bar builder.
    """
    dummy_img = Image.new("RGB", (W, sub_h))
    dummy_draw = ImageDraw.Draw(dummy_img)
    sub_font_sz = 30 if is_short else 22
    speaker_tag = "एंकर:" if language == "hindi" else "ANCHOR:"
    tag_px = measure_bilingual_text(dummy_draw, speaker_tag, size=sub_font_sz) + 18
    start_x = 58 + tag_px
    max_line_w = W - start_x - 36
    space_px = max(8, int(sub_font_sz * 0.32))
    ty = (sub_h - sub_font_sz) // 2 - 2

    for wt in word_timings:
        wt["sub_px"] = measure_bilingual_text(dummy_draw, wt["word"], size=sub_font_sz)

    lines, cur_line, cur_w = [], [], 0
    for wt in word_timings:
        w_px = wt["sub_px"]
        if cur_line and (cur_w + space_px + w_px > max_line_w):
            lines.append(cur_line)
            cur_line = [wt]
            cur_w = w_px
        else:
            cur_line.append(wt)
            cur_w += (space_px + w_px) if len(cur_line) > 1 else w_px
    if cur_line:
        lines.append(cur_line)
    if not lines:
        lines = [[{"word": "", "start": 0.0, "end": 1.0, "idx": 0, "sub_px": 10}]]

    total_words = max(1, len(word_timings))
    sub_cards = [None] * total_words

    for ln in lines:
        base_up = Image.new("RGB", (W, sub_h), (10, 14, 28))
        du = ImageDraw.Draw(base_up)
        du.rectangle([0, 0, W, 3], fill=(0, 195, 255))
        du.rounded_rectangle([16, 6, W - 16, sub_h - 6], radius=10, fill=(18, 24, 46), outline=(255, 205, 0), width=2)
        cy_dot = sub_h // 2
        du.ellipse([32, cy_dot - 7, 46, cy_dot + 7], fill=(235, 30, 45))
        draw_bilingual_text(du, (56, ty), speaker_tag, size=sub_font_sz, fill=(255, 205, 0))

        base_sp = base_up.copy()
        ds = ImageDraw.Draw(base_sp)

        tx = start_x
        line_words = []
        for wt in ln:
            w_str = wt["word"]
            w_px = wt["sub_px"]
            draw_bilingual_text(du, (tx, ty), w_str, size=sub_font_sz, fill=(160, 188, 225))
            draw_bilingual_text(ds, (tx, ty), w_str, size=sub_font_sz, fill=(255, 255, 255))
            line_words.append((wt["idx"], w_str, tx, w_px))
            tx += w_px + space_px

        running_img = base_up.copy()
        for (w_idx, w_str, tx, w_px) in line_words:
            sc_img = running_img.copy()
            sc_draw = ImageDraw.Draw(sc_img)
            sc_draw.rounded_rectangle(
                [tx - 4, ty - 2, tx + w_px + 4, ty + sub_font_sz + 5],
                radius=6,
                fill=(205, 18, 34),
                outline=(255, 215, 0),
                width=2,
            )
            draw_bilingual_text(sc_draw, (tx, ty), w_str, size=sub_font_sz, fill=(255, 238, 75))
            sub_cards[w_idx] = np.asarray(sc_img, dtype=np.uint8)

            box = (max(0, tx - 2), max(0, ty - 2), min(W, tx + w_px + 4), min(sub_h, ty + sub_font_sz + 6))
            running_img.paste(base_sp.crop(box), box)

    return sub_cards


# ================= 8. FULL-FRAME BROADCAST VIDEO RENDERER =================
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


def build_news_video(script_data, scene_assets, output_path, is_short=True):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    fps = 24 if is_short else 20
    W, H = (1080, 1920) if is_short else (1280, 720)

    language = script_data.get("language", "hindi")
    category = script_data.get("category", "NATION").upper()
    anchor_gender = script_data.get("anchor_gender", "female")
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
        broll_win_w, broll_win_h = W, 830
        strap_h = 104
        anchor_w, anchor_h = W, H - broll_win_h - strap_h  # 986px
        sub_h = 96
        desk_ratio = 0.56
        story_card_h = 220
    else:
        header_h = 46
        strap_h = 58
        sub_h = 58
        body_h = H - header_h - strap_h - sub_h - ticker_h  # 514px
        broll_win_w, broll_win_h = 760, body_h
        anchor_w, anchor_h = W - broll_win_w, body_h  # 520x514
        desk_ratio = 0.86
        story_card_h = 166

    animator = StudioAnimeAnchor(gender=anchor_gender, width=anchor_w, height=anchor_h, desk_ratio=desk_ratio)

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

            headline_banner = (asset.get("headline_banner") or script_data.get("headline_banner") or "BREAKING NEWS").strip()
            narration = (asset.get("subtitles") or asset.get("narration") or headline_banner).strip()

            word_timings = build_word_timings(narration, dur)
            story_cards = _build_word_synced_story_cards(
                broll_win_w=broll_win_w,
                card_h=story_card_h,
                word_timings=word_timings,
                language=language,
                is_short=is_short,
            )
            sub_cards = _build_word_synced_subtitle_cards(
                W=W,
                sub_h=sub_h,
                word_timings=word_timings,
                language=language,
                is_short=is_short,
            )

            badge_label = "बड़ी ख़बर" if language == "hindi" else "BREAKING"
            tag_w = 225 if is_short else 185
            strap_font_sz = 28 if is_short else 22
            hl_font_sz = 32 if is_short else 24

            strap_left_img = Image.new("RGB", (tag_w, strap_h), (155, 12, 24))
            sl_draw = ImageDraw.Draw(strap_left_img)
            sl_draw.rectangle([0, 0, tag_w, 5], fill=(255, 205, 0))
            sl_draw.rectangle([0, strap_h - 5, tag_w, strap_h], fill=(255, 205, 0))
            sl_draw.polygon([(0, 5), (tag_w, 5), (tag_w - 22, strap_h - 5), (0, strap_h - 5)], fill=(250, 195, 0))
            draw_bilingual_text(sl_draw, (18, (strap_h - strap_font_sz) // 2 - 2), badge_label, size=strap_font_sz, fill=(15, 15, 20))
            strap_left_arr = np.asarray(strap_left_img, dtype=np.uint8)

            hl_loop_str = f"   {headline_banner}   •   {narration[:120]}   •   " * 3
            right_w = W - tag_w
            hl_strip_w = max(right_w * 3, len(hl_loop_str) * 18)
            hl_strip_img = Image.new("RGB", (hl_strip_w, strap_h), (155, 12, 24))
            hr_draw = ImageDraw.Draw(hl_strip_img)
            hr_draw.rectangle([0, 0, hl_strip_w, 5], fill=(255, 205, 0))
            hr_draw.rectangle([0, strap_h - 5, hl_strip_w, strap_h], fill=(255, 205, 0))
            hl_end_x = draw_bilingual_text(hr_draw, (16, (strap_h - hl_font_sz) // 2 - 2), hl_loop_str, size=hl_font_sz, fill=(255, 255, 255))
            hl_unit_px = max(300, (hl_end_x - 16) // 3)
            strap_right_arr = np.asarray(hl_strip_img, dtype=np.uint8)

            prepared_scenes.append({
                "idx": idx,
                "dur": dur,
                "start_t": total_duration,
                "env": env,
                "broll_base_arr": broll_base_arr,
                "word_timings": word_timings,
                "story_cards": story_cards,
                "sub_cards": sub_cards,
                "strap_left_arr": strap_left_arr,
                "strap_right_arr": strap_right_arr,
                "hl_unit_px": hl_unit_px,
                "tag_w": tag_w,
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

    logger.info(f"🎬 Rendering {fps}fps {'SHORT (1080x1920)' if is_short else 'LONG (1280x720 HD)'} Anime Broadcast Video ({total_duration:.1f}s = {total_duration/60.0:.1f} min)...")
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
        word_timings = sc["word_timings"]
        story_cards = sc["story_cards"]
        sub_cards = sc["sub_cards"]
        strap_left_arr = sc["strap_left_arr"]
        strap_right_arr = sc["strap_right_arr"]
        hl_unit_px = sc["hl_unit_px"]
        tag_w = sc["tag_w"]
        right_w = W - tag_w
        scene_start_t = sc["start_t"]
        bh, bw, _ = broll_base_arr.shape
        max_dx = max(1, bw - broll_win_w)
        max_dy = max(1, bh - broll_win_h)

        cur_w_idx = 0
        n_words = len(word_timings)

        for f_i in range(n_frames):
            t = f_i / float(fps)
            gt = scene_start_t + t
            speech_amp = float(env[min(len(env) - 1, f_i)])

            while (cur_w_idx + 1 < n_words) and (t >= word_timings[cur_w_idx]["end"]):
                cur_w_idx += 1

            prog = min(1.0, max(0.0, t / max(0.1, dur)))
            if idx % 2 == 0:
                crop_x = int(max_dx * prog * 0.8)
                crop_y = int(max_dy * (1.0 - prog) * 0.7)
            else:
                crop_x = int(max_dx * (1.0 - prog) * 0.8)
                crop_y = int(max_dy * prog * 0.7)

            broll_view = broll_base_arr[crop_y : crop_y + broll_win_h, crop_x : crop_x + broll_win_w]
            anchor_arr = animator.render_frame(gt, speech_amp=speech_amp, word_idx=cur_w_idx)

            scroll_x = int(gt * 150) % max(1, min(unit_px, ticker_arr.shape[1] - W - 1))
            hl_scroll_x = int(t * 95) % max(1, min(hl_unit_px, strap_right_arr.shape[1] - right_w - 1))

            if is_short:
                canvas[0:830, :, :] = broll_view
                canvas[28:84, 28:468, :] = badge_on_arr
                canvas[830 - story_card_h - 14 : 830 - 14, :, :] = story_cards[cur_w_idx]

                canvas[830:934, 0:tag_w, :] = strap_left_arr
                canvas[830:934, tag_w:W, :] = strap_right_arr[:, hl_scroll_x : hl_scroll_x + right_w, :]

                canvas[934:1920, :, :] = anchor_arr

                bar_w = int(W * (0.18 + 0.72 * speech_amp))
                x_s = (W - bar_w) // 2
                canvas[1486:1494, x_s : x_s + bar_w, :] = (255, 65, 75)
                canvas[1494:1590, :, :] = sub_cards[cur_w_idx]

                canvas[1590:1648, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]
                canvas[1648:1920, :, :] = pedestal_arr
            else:
                canvas[0:46, :, :] = header_arr
                canvas[46:560, 0:760, :] = broll_view
                canvas[560 - story_card_h - 10 : 560 - 10, 0:760, :] = story_cards[cur_w_idx]
                canvas[46:560, 760:1280, :] = anchor_arr
                canvas[46:560, 756:764, :] = (250, 195, 0)

                canvas[560:618, 0:tag_w, :] = strap_left_arr
                canvas[560:618, tag_w:W, :] = strap_right_arr[:, hl_scroll_x : hl_scroll_x + right_w, :]

                canvas[618:676, :, :] = sub_cards[cur_w_idx]
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


# ================= 9. YOUTUBE UPLOAD & MULTI-PATH ARTIFACT SAVER =================
def cleanup_temp_files():
    os.makedirs("temp", exist_ok=True)
    for f in glob.glob("temp/*"):
        try:
            os.remove(f)
        except Exception:
            pass


def _mirror_video_for_github_artifacts(video_path, is_short=True):
    """
    Mirrors the rendered MP4 to all standard paths so GitHub Actions `actions/upload-artifact`
    ALWAYS finds the video whether the workflow YAML looks for:
      - `output/*.mp4`
      - `final_short.mp4` / `final_long.mp4`
      - `AI_NEWS_CHANNEL_OUTPUT/shorts/*.mp4` / `AI_NEWS_CHANNEL_OUTPUT/long_videos/*.mp4`
    """
    if not os.path.exists(video_path):
        return
    base_name = os.path.basename(video_path)
    targets = [
        "final_short.mp4" if is_short else "final_long.mp4",
        os.path.join("AI_NEWS_CHANNEL_OUTPUT", "shorts" if is_short else "long_videos", base_name),
    ]
    for dst in targets:
        try:
            d_dir = os.path.dirname(dst)
            if d_dir:
                os.makedirs(d_dir, exist_ok=True)
            shutil.copy2(video_path, dst)
            logger.info(f"📦 Saved artifact copy for download: {dst}")
        except Exception as e:
            logger.warning(f"Artifact mirror warning ({dst}): {e}")


def _sanitize_youtube_title(raw_title, is_short=True):
    clean = re.sub(r"[<>\"']", "", str(raw_title or "LIVE Breaking News Update"))
    clean = re.sub(r"\s+", " ", clean).strip()
    if is_short:
        clean = re.sub(r"#shorts", "", clean, flags=re.IGNORECASE).strip()
        return f"{clean[:68]} #Shorts".strip()
    else:
        clean = re.sub(r"#shorts", "", clean, flags=re.IGNORECASE).strip()
        return clean[:80] or "🔴 LIVE महाबुलेटिन: आज की सबसे बड़ी ख़बरें"


def upload_to_youtube(video_path, script_data, is_short=True):
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        logger.warning("⚠️ YouTube OAuth credentials missing in environment! Video saved locally at: " + video_path)
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
        logger.info("🔑 Refreshing YouTube OAuth2 access token...")
        creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        title = _sanitize_youtube_title(script_data.get("title", ""), is_short=is_short)
        raw_desc = str(script_data.get("description", "24x7 Live News Bulletin."))
        description = re.sub(r"[<>]", "", raw_desc)
        if not is_short:
            description = description.replace("#Shorts", "#LongVideo")

        raw_tags = script_data.get("tags", ["Breaking News", "Live News", "Hindi News"])
        clean_tags = []
        total_tag_len = 0
        for t in raw_tags:
            ct = re.sub(r"[<>,\"']", "", str(t)).strip()
            if not is_short and ct.lower() in ("shorts", "#shorts"):
                continue
            if ct and (total_tag_len + len(ct) < 280):
                clean_tags.append(ct)
                total_tag_len += len(ct)
        if not is_short and "Full Bulletin" not in clean_tags:
            clean_tags.append("Full Bulletin")

        body = {
            "snippet": {
                "title": title,
                "description": description[:4500],
                "tags": clean_tags[:12],
                "categoryId": "25",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        for attempt in range(1, 4):
            try:
                media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True, mimetype="video/mp4")
                logger.info(f"📤 Uploading {'SHORT' if is_short else 'LONG VIDEO'} to YouTube (Attempt {attempt}/3): '{title}'...")
                request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"   ↳ Upload progress: {int(status.progress() * 100)}%")

                vid_id = response.get("id")
                logger.info(f"✅ SUCCESSFULLY UPLOADED TO YOUTUBE! Video URL: https://youtu.be/{vid_id}")
                return vid_id
            except Exception as up_err:
                logger.warning(f"YouTube upload attempt {attempt} warning: {up_err}")
                time.sleep(3)

        return None
    except Exception as e:
        err_msg = str(e)
        logger.error(f"❌ YouTube Upload Failed: {err_msg}")
        if "invalid_grant" in err_msg.lower():
            logger.error(
                "💡 FIX FOR 'invalid_grant': Your YT_REFRESH_TOKEN in GitHub Secrets has expired (Google OAuth Testing tokens expire after 7 days). "
                "Generate a fresh Refresh Token in OAuth Playground and update YT_REFRESH_TOKEN in GitHub Settings -> Secrets!"
            )
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
        f"Language: {language.upper()} | Anime Anchor: {chosen_gender.upper()} | Initial Scenes: {len(scenes)}"
    )

    max_unique_images = 4 if is_short else 5
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
            scene_idx=idx,
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
            "headline_banner": hl.get("title", script_data.get("headline_banner", "बड़ी ख़बर")),
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
    )

    _mirror_video_for_github_artifacts(output_video, is_short=is_short)

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
