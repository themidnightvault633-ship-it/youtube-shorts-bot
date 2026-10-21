import os
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY is missing! Set it in environment variables or GitHub Secrets.")

# सबसे स्टेबल और बिना 503 एरर वाला मॉडल
MODEL_NAME = "gemini-1.5-flash"

BASE_DIR = Path("Tech_News_AI_Studio")
BASE_DIR.mkdir(exist_ok=True)

HISTORY_FILE = BASE_DIR / "news_history.json"
LONG_SCRIPT_FILE = BASE_DIR / "latest_long_video_script.md"

WIDTH = 1080
HEIGHT = 1920
FPS = 30
MAX_RETRIES = 5  # रीट्राई अटेम्प्ट्स बढ़ा दिए गए हैं

NEWS_FEEDS = [
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en"
]
