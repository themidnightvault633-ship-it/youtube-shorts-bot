import os
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY is missing! Set it in GitHub Secrets.")

MODEL_NAME = "gemini-1.5-flash"

BASE_DIR = Path("AI_NEWS_CHANNEL_OUTPUT")
BASE_DIR.mkdir(exist_ok=True)

HISTORY_FILE = BASE_DIR / "news_history.json"
LONG_SCRIPT_FILE = BASE_DIR / "latest_long_video_script.md"
ASSETS_DIR = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)

WIDTH = 1080
HEIGHT = 1920
FPS = 30
MAX_RETRIES = 3

NEWS_FEEDS = [
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en"
]
