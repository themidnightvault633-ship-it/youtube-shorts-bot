import os
import json
import time
import random
import re
import html
import logging
import requests
import xml.etree.ElementTree as ET
from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    FALLBACK_MODELS,
    NEWS_FEEDS,
    CATEGORIES,
    SHORT_MIN_SCENES,
    SHORT_MAX_SCENES,
    LONG_MIN_SCENES,
    LONG_MAX_SCENES,
)

logger = logging.getLogger("NewsBot.ScriptEngine")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}

_ANCHOR_TOGGLE = 0


def _pick_anchor_gender(override=None):
    global _ANCHOR_TOGGLE
    if override in ("male", "female"):
        return override
    gender = "female" if (_ANCHOR_TOGGLE % 2 == 0) else "male"
    _ANCHOR_TOGGLE += 1
    return gender


def _clean_html_text(raw_text):
    if not raw_text:
        return ""
    text = html.unescape(str(raw_text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_rss_image(item):
    """Extracts any high-res news image URL embedded in an RSS <item>."""
    for elem in item.iter():
        tag_lower = elem.tag.lower()
        if tag_lower.endswith("content") or tag_lower.endswith("thumbnail") or tag_lower.endswith("enclosure"):
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
    """Fetches real-time news headlines + summary + embedded media URLs from multiple RSS feeds."""
    feed_cfg = NEWS_FEEDS.get(category, NEWS_FEEDS["NATION"])
    urls = feed_cfg.get("urls", []) if isinstance(feed_cfg, dict) else (feed_cfg if isinstance(feed_cfg, list) else [feed_cfg])
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
                pub_date = _clean_html_text(item.findtext("pubDate", ""))
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
                    "published": pub_date,
                    "source": source,
                    "media_url": media_url,
                })
                if len(headlines) >= max_items:
                    break
        except Exception as e:
            logger.warning(f"RSS fetch warning ({url}): {e}")

    if headlines:
        logger.info(f"Fetched {len(headlines)} live headlines for {category}")
    return headlines


def _call_gemini_rest(model_name, prompt, api_key, timeout_sec=35):
    """Direct REST API call to Gemini with strict timeout so GitHub Actions never hangs."""
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
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Empty candidates from Gemini REST API")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Empty content parts from Gemini REST API")
    return parts[0].get("text", "")


def _build_local_fallback_script(category, headlines, is_short, is_breaking, anchor_gender, language):
    """Builds a broadcast-grade Devanagari Hindi or English script directly from live RSS headlines."""
    top = headlines[0] if headlines else {
        "title": "भारत और दुनिया की इस वक्त की बड़ी खबरें",
        "summary": "राष्ट्रीय और अंतरराष्ट्रीय स्तर पर आज कई अहम घटनाक्रम सामने आए हैं।",
        "source": "News Bureau",
        "media_url": "",
    }
    top_title = top["title"]
    media_urls = [h.get("media_url", "") for h in headlines if h.get("media_url")]

    if language == "hindi":
        intro = (
            f"नमस्कार, चौबीस घंटे लाइव न्यूज़ के विशेष बुलेटिन में आपका स्वागत है। "
            f"इस वक्त की सबसे बड़ी और अहम खबर आ रही है: {top_title}।"
        )
        mid_1 = (
            f"ताज़ा जानकारी के मुताबिक, {headlines[1]['title'] if len(headlines) > 1 else top.get('summary', top_title)}। "
            f"प्रशासन और विशेषज्ञों की इस पूरे घटनाक्रम पर लगातार कड़ी नज़र बनी हुई है।"
        )
        mid_2 = (
            f"वहीं अगली बड़ी खबर की बात करें तो, {headlines[2]['title'] if len(headlines) > 2 else 'देशभर में इस मुद्दे को लेकर हलचल तेज़ हो गई है और लगातार नए अपडेट सामने आ रहे हैं'}।"
        )
        mid_3 = (
            f"इसके साथ ही एक और महत्वपूर्ण अपडेट सामने आया है: {headlines[3]['title'] if len(headlines) > 3 else 'आर्थिक और तकनीकी मोर्चे पर भी आज कई बड़े फैसले लिए गए हैं जिनका सीधा असर आम जनता पर पड़ेगा'}।"
        )
        mid_4 = (
            f"विशेषज्ञों का मानना है कि {headlines[4]['title'] if len(headlines) > 4 else 'आने वाले कुछ घंटों में इस पूरे मामले पर आधिकारिक बयान जारी किया जा सकता है'}।"
        )
        outro = "इन तमाम बड़ी खबरों पर हमारी नज़र लगातार बनी हुई है। हर सटीक और तेज़ लाइव अपडेट के लिए चैनल को अभी सब्सक्राइब करें और वीडियो को शेयर करें। नमस्कार।"
        narrations = [intro, mid_1, mid_2, outro] if is_short else [intro, mid_1, mid_2, mid_3, mid_4, outro]
        banner = "बड़ी ख़बर: लाइव अपडेट" if not is_breaking else "ब्रेकिंग न्यूज़: बड़ी ख़बर"
    else:
        intro = f"Welcome to our 24/7 Live Global News broadcast. Our top breaking story this hour: {top_title}."
        mid_1 = (
            f"According to the latest official dispatches, {headlines[1]['title'] if len(headlines) > 1 else top.get('summary', top_title)}. "
            f"Authorities and international observers are closely tracking every development."
        )
        mid_2 = (
            f"Meanwhile, in another major headline, {headlines[2]['title'] if len(headlines) > 2 else 'new diplomatic and economic responses are unfolding across major global capitals'}."
        )
        mid_3 = (
            f"Furthermore, correspondents report that {headlines[3]['title'] if len(headlines) > 3 else 'key policy leaders are convening emergency sessions to address the broader regional impact'}."
        )
        mid_4 = (
            f"In addition, {headlines[4]['title'] if len(headlines) > 4 else 'global markets and strategic analysts are reacting to these rapid developments'}."
        )
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
            "image_prompt": (
                f"Photorealistic editorial news photography of {kw}, "
                f"BBC and Aaj Tak broadcast journalism style, dramatic lighting, ultra-detailed, 8k, no text"
            ),
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    ticker_items = [h["title"] for h in headlines[:6]] if headlines else [top_title]
    ticker_sep = "  |  "
    return {
        "category": category,
        "language": language,
        "anchor_gender": anchor_gender,
        "is_breaking": is_breaking,
        "is_short": is_short,
        "title": f"🔴 LIVE: {top_title[:75]} #Shorts" if is_short else f"🔴 LIVE Special Report: {top_title[:72]}",
        "description": (
            f"{top_title}\n\n"
            f"Watch 24x7 Live News updates in Aaj Tak, News 24 & BBC broadcast style.\n"
            f"{'#BreakingNews #LiveNews #HindiNews #Shorts' if is_short else '#BreakingNews #LiveNews #HindiNews #SpecialReport'}"
        ),
        "tags": ["Breaking News", "Live News", "Hindi News", "Aaj Tak", "News 24", "BBC News", category] + (["Shorts"] if is_short else ["Special Report", "Full Bulletin"]),
        "headline_banner": banner,
        "ticker_text": ticker_sep.join(ticker_items),
        "scenes": scenes,
    }


def generate_news_script(category=None, is_short=True, is_breaking=False, anchor_gender=None):
    """Generates a complete TV Broadcast News script in pure Devanagari Hindi or Broadcast English."""
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
            "DO NOT use Romanized Hinglish alphabets because the Hindi neural TTS voice requires pure Devanagari script "
            "to pronounce words like a professional Aaj Tak / News 24 television anchor."
        )
    else:
        lang_instruction = (
            "Write ALL `narration`, `subtitles`, `headline_banner`, and `ticker_text` in crisp, authoritative "
            "BBC World News broadcast English. Sound like a live prime-time international news anchor."
        )

    prompt = f"""You are the Executive Producer for a 24/7 Live Television News Network (styled after BBC News, Aaj Tak, and News 24).
Create a {num_scenes}-scene {'YouTube Short (9:16)' if is_short else 'Full Prime-Time Special Report Long Video (16:9)'} TV news broadcast script based on these real-time headlines:
{headlines_context}

CRITICAL RULES:
1. {lang_instruction}
2. Anchor Gender for this broadcast: "{chosen_gender}".
3. Total scenes: EXACTLY {num_scenes}. Each scene's `narration` must be {words_per_scene}.
4. For every scene, provide:
   - `scene_id`: integer (1 to {num_scenes})
   - `narration`: spoken anchor script (Pure Devanagari Hindi if language=='hindi', else English)
   - `subtitles`: same as narration
   - `headline_banner`: short 4-8 word punchy breaking strap for that scene (Devanagari Hindi if hindi, else English)
   - `search_query`: 4-6 English keywords describing the real-world event/person/location for fetching real news event photography
   - `image_prompt`: Detailed English prompt for generating photorealistic editorial news photography of the event (NO text/words in image)
   - `camera_angle`: alternate between "wide" and "closeup"

Return ONLY valid JSON with this exact structure:
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
      "search_query": "...",
      "image_prompt": "...",
      "camera_angle": "wide"
    }}
  ]
}}"""

    models_to_try = ["gemini-3.8-flash"]
    for m in [MODEL_NAME] + list(FALLBACK_MODELS):
        if m and m not in models_to_try:
            models_to_try.append(m)

    if GEMINI_API_KEY:
        for model_name in models_to_try:
            try:
                logger.info(f"Requesting {'SHORT' if is_short else 'LONG'} script from {model_name} (lang={language}, anchor={chosen_gender})...")
                raw_json = _call_gemini_rest(model_name, prompt, GEMINI_API_KEY, timeout_sec=35)
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip(), flags=re.MULTILINE)
                data = json.loads(cleaned)
                scenes = data.get("scenes", [])
                if not scenes:
                    raise ValueError("No scenes in JSON response")

                for idx, sc in enumerate(scenes):
                    hl = headlines[idx] if idx < len(headlines) else (headlines[0] if headlines else {})
                    sc["scene_id"] = idx + 1
                    sc["rss_image_url"] = hl.get("media_url", "")
                    if not sc.get("search_query"):
                        sc["search_query"] = hl.get("title", "Breaking News India World")
                    if not sc.get("headline_banner"):
                        sc["headline_banner"] = data.get("headline_banner", "BREAKING NEWS")
                    if not sc.get("camera_angle"):
                        sc["camera_angle"] = "closeup" if idx % 2 == 1 else "wide"

                data["category"] = cat_upper
                data["language"] = language
                data["anchor_gender"] = chosen_gender
                data["is_breaking"] = is_breaking
                data["is_short"] = is_short
                logger.info(f"✅ Generated {len(scenes)}-scene {language.upper()} {'SHORT' if is_short else 'LONG'} script via {model_name}")
                return data
            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}. Trying next fallback...")
                time.sleep(1)

    logger.info("Using smart live-RSS broadcast script builder...")
    return _build_local_fallback_script(cat_upper, headlines, is_short, is_breaking, chosen_gender, language)
