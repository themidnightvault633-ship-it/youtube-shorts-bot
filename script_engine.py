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
    - Single Consistent Lead Anchor (Male ya Female)
    - Topic-specific visuals & b-roll prompts
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

    anchor_gender = force_anchor_gender or random.choice(["female", "male"])
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

RULES:
- Narration language MUST strictly follow {target_language}.
- Keep anchor persona consistent as `{anchor_gender}` across all scenes.
- Each scene's `image_prompt` MUST be realistic news photography or studio b-roll describing the actual news event, photorealistic 8k vertical 9:16, no text.
- Return ONLY valid JSON format.

JSON STRUCTURE:
{{
  "topic_selected": "Chosen headline",
  "category": "{target_category}",
  "is_breaking": {str(is_breaking).lower()},
  "language": "{target_language}",
  "anchor_gender": "{anchor_gender}",
  "title": "Shocking Clickable Short Title with Emojis #Shorts",
  "description": "Engaging description with key takeaways and SEO tags",
  "hashtags": ["#News", "#TechNews", "#Shorts"],
  "scenes": [
    {{
      "scene_num": 1,
      "hook_type": "Headline Alert",
      "narration": "Opening hook in {target_language}",
      "image_prompt": "Photorealistic 9:16 vertical visual of the news event, cinematic broadcast lighting, no text"
    }},
    {{
      "scene_num": 2,
      "hook_type": "Context & Facts",
      "narration": "Deep fact explanation in {target_language}",
      "image_prompt": "Detailed contextual b-roll visual, 8k vertical 9:16, no text"
    }},
    {{
      "scene_num": 3,
      "hook_type": "Impact & Conflict",
      "narration": "Why this matters to the viewer in {target_language}",
      "image_prompt": "Dramatic journalistic photo showing global or national impact, 9:16 vertical, no text"
    }},
    {{
      "scene_num": 4,
      "hook_type": "Conclusion & Question",
      "narration": "Closing remark and call to comment/subscribe in {target_language}",
      "image_prompt": "Newsroom anchor studio desk with glowing world map monitors, 9:16 vertical, no text"
    }}
  ],
  "long_video_package": {{
    "long_title": "Catchy 16:9 Long Video Title",
    "thumbnail_idea": "Photorealistic thumbnail composition description with text placement",
    "full_script_markdown": "Full 8-minute comprehensive investigative script with timecodes and B-roll notes"
  }}
}}
"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
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
                        f.write(f"# 🎬 LONG VIDEO BLUEPRINT ({data.get('category')})\n\n")
                        f.write(f"## 📌 Topic: {data.get('topic_selected')}\n")
                        f.write(f"### 🎯 Title: {long_pkg.get('long_title')}\n")
                        f.write(f"### 🖼️ Thumbnail Concept:\n{long_pkg.get('thumbnail_idea')}\n\n")
                        f.write(f"---\n\n## 📝 Full 8-Minute Script:\n\n{long_pkg.get('full_script_markdown')}\n")

                logging.info(f"✓ Script generated successfully: {data.get('title')}")
                return data

        except Exception as e:
            logging.warning(f"Script generation retry {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(10)

    raise RuntimeError("❌ Script generation failed after maximum retries.")
