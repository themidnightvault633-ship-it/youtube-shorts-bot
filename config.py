import os
from pathlib import Path

# ================= 1. API & MODEL SETTINGS =================
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY missing hai! GitHub Secrets ya Environment Variable mein set karein.")

# Official stable model
MODEL_NAME = "gemini-2.0-flash"

# ================= 2. DIRECTORIES & PATHS =================
BASE_DIR = Path("AI_NEWS_CHANNEL_OUTPUT")
BASE_DIR.mkdir(exist_ok=True)

SHORTS_DIR = BASE_DIR / "shorts"
LONG_DIR = BASE_DIR / "long_videos"
ASSETS_DIR = Path("assets")

SHORTS_DIR.mkdir(exist_ok=True)
LONG_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

HISTORY_FILE = BASE_DIR / "news_history.json"
LONG_SCRIPT_FILE = BASE_DIR / "latest_long_video_script.md"
METADATA_FILE = BASE_DIR / "video_metadata.json"

# ================= 3. RESOLUTIONS & VIDEO SETTINGS =================
FPS = 30
MAX_RETRIES = 5

# Shorts (Vertical 9:16)
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920

# Long Videos (Horizontal 16:9)
LONG_WIDTH = 1920
LONG_HEIGHT = 1080

# ================= 4. NEWS CATEGORIES & LANGUAGE ROUTING =================
NEWS_FEEDS = {
    "NATION": {
        "url": "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
        "category": "national",
        "language": "hinglish",
        "description": "Indian National Breaking & Important News"
    },
    "WORLD": {
        "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
        "category": "international",
        "language": "english",
        "description": "Global International Geopolitics & Major Events"
    },
    "TECHNOLOGY": {
        "url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
        "category": "tech",
        "language": "hinglish",
        "description": "Tech, AI, Gadgets & Science Innovations"
    }
}

# ================= 5. ANCHOR & VOICE PERSONAS =================
VOICE_PERSONAS = {
    "hinglish": {
        "female": "hi-IN-SwaraNeural",
        "male": "hi-IN-MadhurNeural"
    },
    "english": {
        "female": "en-US-JennyNeural",
        "male": "en-US-GuyNeural"
    }
}

# ================= 6. 24/7 BACKGROUND MONITOR & SCHEDULES =================
MONITOR_CHECK_INTERVAL_SECONDS = 600  # Har 10 minute mein RSS scan
BREAKING_NEWS_KEYWORDS = [
    "breaking", "urgent", "war", "earthquake", "attack", "crisis", 
    "resigns", "explosion", "emergency", "dead", "banned", "launched", "crash"
]

SCHEDULE_MORNING_TIME = "08:00"
SCHEDULE_EVENING_TIME = "20:00"
