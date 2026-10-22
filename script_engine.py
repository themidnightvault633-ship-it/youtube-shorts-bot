import json
import random
import time
import logging
import xml.etree.ElementTree as ET
import requests
from google import genai
from google.genai import types
from config import API_KEY, MODEL_NAME, HISTORY_FILE, LONG_SCRIPT_FILE, NEWS_FEEDS, MAX_RETRIES

client = genai.Client(api_key=API_KEY)

def read_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def fetch_live_trending_news():
    headlines = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in NEWS_FEEDS:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:8]:
                    title = item.find("title")
                    if title is not None and title.text:
                        headlines.append(title.text)
        except Exception as e:
            logging.warning(f"RSS fetch warning: {e}")
    return headlines

def generate_content_script(episode_number):
    history = read_json(HISTORY_FILE, {"episodes": []})
    used_titles = [ep.get("title", "") for ep in history.get("episodes", [])]

    live_headlines = fetch_live_trending_news()
    random.shuffle(live_headlines)
    selected_headlines = live_headlines[:12] if live_headlines else [
        "AI Deepfake Scams and Cybersecurity Alert in India",
        "Global Semiconductor Chip War: US, China, and India's New Strategy",
        "ISRO and Future Space-Tech Breakthroughs"
    ]

    prompt = f"""
You are an elite YouTube News Director. Look at these trending news headlines:
{json.dumps(selected_headlines, ensure_ascii=False)}

Pick the MOST shocking topic that is NOT in this used list:
{json.dumps(used_titles[-20:], ensure_ascii=False)}

Determine if the topic is **National (India)** or **International (World/Global)**.
- If it's **National**, write the script scenes in **Engaging Hinglish/Hindi** and use anchor types: `female_hi` or `male_hi`.
- If it's **International**, write the script scenes in **Professional English** and use anchor types: `female_en` or `male_en`.

Generate TWO outputs:
1. A high-retention **YouTube Short (35-45 seconds, 4 scenes)**.
2. A complete **Long Video Blueprint (8-10 minutes)** on the same topic.

Return ONLY valid JSON:
{{
  "topic_selected": "News headline chosen",
  "category": "National or International",
  "title": "Click-worthy Short Title with emojis #shorts",
  "description": "High-SEO description with hashtags",
  "hashtags": ["#News", "#TechNews", "#Shorts"],
  "scenes": [
    {{
      "narration": "Scene 1 text in appropriate language",
      "anchor": "female_hi or female_en",
      "image_prompt": "Newsroom anchor desk, professional news anchor, 8k vertical 9:16, no text"
    }},
    {{
      "narration": "Scene 2 text",
      "anchor": "male_hi or male_en",
      "image_prompt": "Professional news anchor presenting breaking news, studio monitors, 8k vertical 9:16, no text"
    }},
    {{
      "narration": "Scene 3 text",
      "anchor": "female_hi or female_en",
      "image_prompt": "High-tech news studio background, 8k vertical 9:16, no text"
    }},
    {{
      "narration": "Scene 4 text",
      "anchor": "male_hi or male_en",
      "image_prompt": "Newsroom desk closing shot, 8k vertical 9:16, no text"
    }}
  ],
  "long_video_package": {{
    "long_title": "3 High-CTR Long Video Title Options",
    "thumbnail_idea": "Exact visual layout and text for YouTube Thumbnail",
    "full_script_markdown": "Complete 8-minute structured script with B-Roll cues"
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
                    temperature=0.8,
                ),
            )
            data = json.loads(response.text)

            if "scenes" in data and len(data["scenes"]) >= 3:
                data["scenes"] = data["scenes"][:4]
                long_pkg = data.get("long_video_package", {})
                if long_pkg:
                    with open(LONG_SCRIPT_FILE, "w", encoding="utf-8") as f:
                        f.write(f"# 🎬 LONG VIDEO BLUEPRINT\n\n")
                        f.write(f"## 📌 Topic: {data.get('topic_selected')} ({data.get('category')})\n\n")
                        f.write(f"### 🎯 Title Ideas:\n{long_pkg.get('long_title')}\n\n")
                        f.write(f"### 🖼️ Thumbnail Concept:\n{long_pkg.get('thumbnail_idea')}\n\n")
                        f.write(f"---\n\n## 📝 Full Script:\n\n{long_pkg.get('full_script_markdown')}\n")

                return data
        except Exception as e:
            logging.warning(f"Script retry {attempt}/{MAX_RETRIES} due to server load/error: {e}")
            time.sleep(15)  # 15 seconds gap to auto-recover from 503 high demand

    raise RuntimeError("❌ Script generation failed after max retries.")
