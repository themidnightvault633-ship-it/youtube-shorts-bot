import os
from datetime import datetime
from pathlib import Path

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

BASE_DIR = Path("Spiritual_AI_Video")
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_FILE = BASE_DIR / "episode_history.json"
TRACKER_FILE = BASE_DIR / "episode_tracker.json"
LOG_DIR = BASE_DIR / "logs"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

VOICE = "hi-IN-MadhurNeural"
MAX_SCENES = 5
MAX_RETRIES = 3

MUSIC_FILE = os.getenv("MUSIC_FILE", "bgm.mp3")
MUSIC_VOLUME = 0.10

SPIRITUAL_CATEGORIES = [
    "रामायण के अनकहे रहस्य और भगवान राम के चमत्कार",
    "महाभारत के अनसुने सच, श्राप और गुप्त योद्धा गाथाएं",
    "भगवान शिव, रुद्र अवतार और कैलाश पर्वत के रहस्य",
    "प्राचीन रहस्यमयी भारतीय मंदिर और उनके हैरान कर देने वाले चमत्कार",
    "गरुड़ पुराण और परलोक, आत्मा तथा कर्म के भयानक सच",
    "सनातन धर्म, वेद और आधुनिक विज्ञान के अद्भुत आश्चर्य"
]

def get_dynamic_festivals():
    """Current running year ke hisaab se festivals ki dates automatically generate karta hai."""
    current_year = datetime.now().year
    return [
        {"name": "Maha Shivratri", "date": f"{current_year}-03-01", "hindi": "महाशिवरात्रि विशेष"},
        {"name": "Holi", "date": f"{current_year}-03-14", "hindi": "होली विशेष"},
        {"name": "Ram Navami", "date": f"{current_year}-04-06", "hindi": "राम नवमी विशेष"},
        {"name": "Diwali", "date": f"{current_year}-10-20", "hindi": "दीपावली विशेष"}
    ]
