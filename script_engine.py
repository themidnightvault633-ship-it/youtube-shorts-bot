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
        "ISRO and Future Space-Tech Breakthroughs",
        "Major Geopolitical Shift in Global Economy"
    ]

    prompt = f"""
You are an elite Geopolitics, National News & Tech Investigation YouTube Director (like Dhruv Rathee and Nitish Rajput).

Here are today's trending news topics:
{json.dumps(selected_headlines, ensure_ascii=False)}

Pick the MOST shocking topic that is NOT in this used list:
{json.dumps(used_titles[-20:], ensure_ascii=False)}

Generate TWO outputs in engaging Hinglish/Devanagari Hindi:
1. A high-retention **YouTube Short (35-45 seconds, 4 scenes)** using HOOK -> SETUP -> PROOF -> PAYOFF.
2. A complete **Long Video Blueprint (8-10 minutes)** on the same topic.

VISUAL STYLE FOR SHORT SCENES:
Every `image_prompt` MUST be in English:
"Hyper-realistic documentary digital illustration, dramatic newsroom & geopolitical lighting, 8k vertical 9:16, NO text, [detailed visual]"

Return ONLY valid JSON:
{{
  "topic_selected": "News headline chosen",
  "title": "Click-worthy Hindi/Hinglish Short Title with emojis #shorts",
  "description": "High-SEO description with hashtags",
  "script": "Combined Hindi narration for the Short",
  "hashtags": ["#TechNews", "#Geopolitics", "#CurrentAffairs", "#Shorts"],
  "scenes": [
    {{
      "narration": "Scene 1 (0-3s Hook in Hindi)",
      "image_prompt": "Hyper-realistic documentary digital illustration, dramatic lighting, 8k vertical 9:16, [Scene 1]"
    }},
    {{
      "narration": "Scene 2 (Core problem in Hindi)",
      "image_prompt": "Hyper-realistic documentary digital illustration, dramatic lighting, 8k vertical 9:16, [Scene 2]"
    }},
    {{
      "narration": "Scene 3 (Impact on India & World in Hindi)",
      "image_prompt": "Hyper-realistic documentary digital illustration, dramatic lighting, 8k vertical 9:16, [Scene 3]"
    }},
    {{
      "narration": "Scene 4 (Verdict + CTA in Hindi)",
      "image_prompt": "Hyper-realistic documentary digital illustration, dramatic lighting, 8k vertical 9:16, [Scene 4]"
    }}
  ],
  "long_video_package": {{
    "long_title": "3 High-CTR Long Video Title Options",
    "thumbnail_idea": "Exact visual layout and 3-word text for YouTube Thumbnail",
    "full_script_markdown": "Complete 8-minute structured Hindi script with B-Roll cues"
  }}
}}
"""

    for attempt in range(MAX_RETRIES):
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
                data["script"] = " ".join(s["narration"].strip() for s in data["scenes"])

                long_pkg = data.get("long_video_package", {})
                if long_pkg:
                    with open(LONG_SCRIPT_FILE, "w", encoding="utf-8") as f:
                        f.write(f"# 🎬 LONG VIDEO BLUEPRINT\n\n")
                        f.write(f"## 📌 Topic: {data.get('topic_selected')}\n\n")
                        f.write(f"### 🎯 Title Ideas:\n{long_pkg.get('long_title')}\n\n")
                        f.write(f"### 🖼️ Thumbnail Concept:\n{long_pkg.get('thumbnail_idea')}\n\n")
                        f.write(f"---\n\n## 📝 Full Script:\n\n{long_pkg.get('full_script_markdown')}\n")

                return data
        except Exception as e:
            logging.warning(f"Script retry {attempt + 1}: {e}")
            time.sleep(2)

    raise RuntimeError("❌ Script generation failed!")
