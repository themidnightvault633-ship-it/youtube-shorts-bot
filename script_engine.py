import json
import random
import time
import logging
from datetime import datetime
from google import genai
from google.genai import types
from config import API_KEY, MODEL_NAME, HISTORY_FILE, SPIRITUAL_CATEGORIES, get_dynamic_festivals, MAX_RETRIES

client = genai.Client(api_key=API_KEY)

def read_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default

def check_upcoming_festival():
    today = datetime.now().date()
    festivals = get_dynamic_festivals()
    for fest in festivals:
        try:
            fest_date = datetime.strptime(fest["date"], "%Y-%m-%d").date()
            diff = (fest_date - today).days
            if 0 <= diff <= 15:
                return fest["hindi"]
        except:
            pass
    return None

def generate_content_script(episode_number):
    history = read_json(HISTORY_FILE, {"episodes": []})
    previous_stories = [item.get("title", "") for item in history.get("episodes", [])]

    festival_focus = check_upcoming_festival()
    if festival_focus:
        context_prompt = f"Trending Festival Special: {festival_focus}. Focus on mind-blowing devotion and deep spiritual engagement."
    else:
        chosen_category = random.choice(SPIRITUAL_CATEGORIES)
        context_prompt = f"Genre / Category: {chosen_category}. Pick an extremely gripping, jaw-dropping, and mysterious untold story."

    prompt = f"""
You are an elite YouTube Shorts viral growth director and master storyteller specializing in Sanatan Dharma.
Create a high-retention vertical YouTube Short script in pure Shuddh Hindi.

Episode number: {episode_number}
{context_prompt}

CRITICAL RULES FOR QA & VISUAL STYLE:
1. **The Hook (First 2 seconds):** Must start with a shocking, spine-chilling statement or question in Hindi.
2. **Storytelling:** Fast-paced, emotional, mysterious, pure Devanagari Hindi. Target duration: 30-45 seconds.
3. **Structure:** Exactly 4 to 5 chronological scenes.
4. **Image Prompts Style:** Must specify stunning **3D Pixar spiritual animation style, cinematic divine lighting, ultra-detailed characters, 8k resolution, vertical 9:16** for every scene prompt in English.
5. **No repetitive topics** from this history list: {json.dumps(previous_stories[-25:], ensure_ascii=False)}

Return ONLY a valid JSON object in this exact structure:
{{
  "title": "Shocking Hindi title with emojis #shorts",
  "description": "SEO description with powerful hashtags",
  "script": "Complete Hindi narration text",
  "hashtags": ["#SanatanDharma", "#ViralShorts"],
  "scenes": [
    {{
      "narration": "Scene narration in pure Hindi",
      "image_prompt": "3D Pixar spiritual animation style, ultra-detailed character, cinematic divine lighting, 4k vertical 9:16"
    }}
  ]
}}
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(response.text)
            if not all(k in data for k in ["title", "description", "script", "scenes"]):
                raise ValueError("Missing required fields")
            
            data["scenes"] = data["scenes"][:5]
            data["script"] = " ".join(s["narration"].strip() for s in data["scenes"])
            return data
        except Exception as error:
            logging.exception("Script generation failed, retrying...")
            time.sleep(2 * (attempt + 1))

    # High-quality fallback script with 3D Pixar style prompts
    return {
        "title": "इस रहस्य को जानकर कांप उठेगी रूह! 🕉️ #shorts",
        "description": "जानिए महादेव से जुड़ा वो रहस्य जो विज्ञान के लिए पहेली है। #sanatan #mahadev",
        "script": "क्या आप जानते हैं कि कैलाश पर्वत पर आज भी एक ऐसी रहस्यमयी शक्ति मौजूद है जहाँ इंसानों का जाना नामुमकिन है? वैज्ञानिक आज तक यह नहीं समझ पाए कि वहाँ समय क्यों रुक जाता है। हर हर महादेव!",
        "hashtags": ["#Mahadev", "#Shiva", "#SanatanDharma"],
        "scenes": [
            {"narration": "क्या आप जानते हैं कि कैलाश पर्वत पर आज भी एक ऐसी रहस्यमयी शक्ति मौजूद है जहाँ इंसानों का जाना नामुमकिन है?", "image_prompt": "3D Pixar spiritual animation style, majestic Mount Kailash under cosmic dark sky, cinematic divine lighting, 4k vertical 9:16"},
            {"narration": "वैज्ञानिक आज तक यह नहीं समझ पाए कि वहाँ समय क्यों रुक जाता है।", "image_prompt": "3D Pixar spiritual animation style, mystical glowing fog over snowy peaks, dramatic atmospheric lighting, vertical 9:16"},
            {"narration": "पौराणिक मान्यता है कि यह स्थान साक्षात शिव का धाम है। हर हर महादेव!", "image_prompt": "3D Pixar spiritual animation style, divine silhouette of Lord Shiva meditating with cosmic energy rays, epic art, vertical 9:16"}
        ]
    }
