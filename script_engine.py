import json
import random
import time
import logging
import re
import xml.etree.ElementTree as ET
import requests
from google import genai
from google.genai import types

from config import (
    API_KEY, MODEL_NAME, HISTORY_FILE, LONG_SCRIPT_FILE,
    NEWS_FEEDS, MAX_RETRIES, BREAKING_NEWS_KEYWORDS
)

try:
    from config import FALLBACK_MODELS
except ImportError:
    FALLBACK_MODELS = [MODEL_NAME, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

client = genai.Client(api_key=API_KEY)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def read_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def clean_json_text(text: str) -> str:
    """Markdown code fences (```json ... ```) ko safely remove karta hai."""
    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def fetch_live_news_by_category():
    """
    RSS feeds ko National, International aur Tech me categorize karke fetch karta hai.
    Sath hi Breaking News headlines ko flag karta hai.
    """
    categorized_news = {
        "NATION": [],
        "WORLD": [],
        "TECHNOLOGY": [],
        "BREAKING": []
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    feed_items = NEWS_FEEDS.items() if isinstance(NEWS_FEEDS, dict) else [
        ("NATION", {"url": NEWS_FEEDS[2] if len(NEWS_FEEDS) > 2 else NEWS_FEEDS[0]}),
        ("WORLD", {"url": NEWS_FEEDS[1] if len(NEWS_FEEDS) > 1 else NEWS_FEEDS[0]}),
        ("TECHNOLOGY", {"url": NEWS_FEEDS[0]})
    ]

    for cat_key, info in feed_items:
        url = info["url"] if isinstance(info, dict) else info
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:10]:
                    title_elem = item.find("title")
                    if title_elem is not None and title_elem.text:
                        headline = title_elem.text.strip()
                        categorized_news[cat_key].append(headline)

                        headline_lower = headline.lower()
                        if any(kw in headline_lower for kw in BREAKING_NEWS_KEYWORDS):
                            categorized_news["BREAKING"].append({
                                "title": headline,
                                "source_category": cat_key
                            })
        except Exception as e:
            logging.warning(f"Error fetching {cat_key} feed: {e}")

    return categorized_news


def generate_content_script(forced_category=None, force_anchor_gender=None):
    """
    AI News Director:
    - National / Tech -> Punchy Hinglish
    - International -> Broadcast English
    - Single Consistent Lead Anchor
    - Pure event B-roll prompts for top screen (since bottom screen has live studio anchor)
    """
    history = read_json(HISTORY_FILE, {"episodes": []})
    used_titles = [ep.get("title", "") for ep in history.get("episodes", [])]

    all_news = fetch_live_news_by_category()

    is_breaking = False
    if forced_category == "BREAKING" or (not forced_category and all_news["BREAKING"]):
        is_breaking = True
        target_category = all_news["BREAKING"][0]["source_category"] if all_news["BREAKING"] else "NATION"
        candidate_headlines = [b["title"] for b in all_news["BREAKING"]]
    elif forced_category in ["NATION", "WORLD", "TECHNOLOGY"]:
        target_category = forced_category
        candidate_headlines = all_news[forced_category]
    else:
        target_category = random.choice(["NATION", "TECHNOLOGY", "WORLD"])
        candidate_headlines = all_news[target_category]

    if not candidate_headlines:
        candidate_headlines = [
            "AI Agent Revolution: Autonomous Robots Taking Over Software Industry",
            "India's New Semiconductor Fab Launch Milestone",
            "Global Space Race Escalates with New Moon Exploration Missions"
        ]

    anchor_gender = force_anchor_gender or "female"
    target_language = "English" if target_category == "WORLD" else "Hinglish (Hindi written in English alphabets with high energy)"

    prompt = f"""
You are an elite TV Broadcast News Director.

CATEGORY: {target_category} (Is Breaking: {is_breaking})
TARGET LANGUAGE: {target_language}
LEAD ANCHOR GENDER: {anchor_gender}

RECENT HEADLINES:
{json.dumps(candidate_headlines[:8], ensure_ascii=False)}

RECENTLY USED TITLES (DO NOT REPEAT):
{json.dumps(used_titles[-25:], ensure_ascii=False)}

TASK:
1. Select the single most shocking/impactful headline.
2. Produce a **35-45 second YouTube Short Script** (4 structured scenes).
3. Produce a **Long-form In-depth Video Blueprint** (8-10 minutes) on the same topic.

CRITICAL VISUAL RULES:
- The bottom half of our video ALREADY shows the live TV News Anchor in the studio.
- Therefore, each scene's `image_prompt` MUST describe ONLY the real-world news event, location, machinery, technology, parliament, infrastructure, or dramatic action B-roll — NEVER include a news anchor, studio presenter, or human portrait looking at the camera in `image_prompt`!
- Narration language MUST strictly follow {target_language}.
- Keep anchor persona consistent as `{anchor_gender}` across all scenes.
- Return ONLY valid JSON format.

JSON STRUCTURE:
{{
  "topic_selected": "Chosen headline",
  "category": "{target_category}",
  "is_breaking": {str(is_breaking).lower()},
  "language": "{target_language}",
  "anchor_gender": "{anchor_gender}",
  "title": "Shocking Clickable Short Title #Shorts",
  "description": "Engaging description with key takeaways and SEO tags",
  "hashtags": ["#News", "#BreakingNews", "#Shorts"],
  "scenes": [
    {{
      "scene_num": 1,
      "hook_type": "Headline Alert",
      "narration": "Opening hook in {target_language}",
      "image_prompt": "Wide-angle photorealistic news B-roll of the actual event location or technology, cinematic lighting, 8k, no people staring at camera, no text"
    }},
    {{
      "scene_num": 2,
      "hook_type": "Context & Facts",
      "narration": "Deep fact explanation in {target_language}",
      "image_prompt": "Close-up detailed journalistic B-roll showing the core subject/hardware/facility in action, 8k photorealistic, no text"
    }},
    {{
      "scene_num": 3,
      "hook_type": "Impact & Conflict",
      "narration": "Why this matters to the viewer in {target_language}",
      "image_prompt": "Dramatic aerial or wide journalistic photo showing national or global scale impact, 8k photorealistic, no text"
    }},
    {{
      "scene_num": 4,
      "hook_type": "Conclusion & Question",
      "narration": "Closing remark and call to comment/subscribe in {target_language}",
      "image_prompt": "Futuristic high-tech global map projection and financial/strategic data screens in a dark command center, 8k photorealistic, no people, no text"
    }}
  ],
  "long_video_package": {{
    "long_title": "Catchy 16:9 Long Video Title",
    "thumbnail_idea": "Photorealistic thumbnail composition description with text placement",
    "full_script_markdown": "Full 8-minute comprehensive investigative script with timecodes and B-roll notes"
  }}
}}
"""

    models_to_try = []
    for m in [MODEL_NAME] + list(FALLBACK_MODELS):
        if m and m not in models_to_try:
            models_to_try.append(m)

    for attempt in range(1, MAX_RETRIES + 1):
        current_model = models_to_try[(attempt - 1) % len(models_to_try)]
        try:
            response = client.models.generate_content(
                model=current_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            clean_text = clean_json_text(response.text)
            data = json.loads(clean_text)

            if "scenes" in data and len(data["scenes"]) >= 3:
                data["scenes"] = data["scenes"][:4]
                long_pkg = data.get("long_video_package", {})
                if long_pkg:
                    with open(LONG_SCRIPT_FILE, "w", encoding="utf-8") as f:
                        f.write(f"# LONG VIDEO BLUEPRINT ({data.get('category')})\n\n")
                        f.write(f"## Topic: {data.get('topic_selected')}\n")
                        f.write(f"### Title: {long_pkg.get('long_title')}\n")
                        f.write(f"### Thumbnail Concept:\n{long_pkg.get('thumbnail_idea')}\n\n")
                        f.write(f"---\n\n## Full 8-Minute Script:\n\n{long_pkg.get('full_script_markdown')}\n")

                logging.info(f"✓ Script generated ({current_model}): {data.get('title')}")
                return data

        except Exception as e:
            logging.warning(f"Script generation retry {attempt}/{MAX_RETRIES} ({current_model}): {e}")
            time.sleep(4)

    raise RuntimeError("❌ Script generation failed after maximum retries.")
