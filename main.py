import json
import shutil
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from config import OUTPUT_DIR, HISTORY_FILE, TRACKER_FILE, LOG_DIR
from script_engine import generate_content_script
from image_engine import download_scene_image
from voice_engine import generate_audio
from video_editor import render_video, validate_video

BASE_DIR = Path("Spiritual_AI_Video")
BASE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "generation.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

def read_json(path, default):
    if not path.exists(): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def write_json(path, data):
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    temp.replace(path)

def get_next_episode():
    return max(1, int(read_json(TRACKER_FILE, {"episode": 1}).get("episode", 1)))

def commit_episode(ep_num, title, script):
    history = read_json(HISTORY_FILE, {"episodes": []})
    history["episodes"].append({"episode": ep_num, "title": title, "script": script, "created_at": datetime.now().isoformat()})
    write_json(HISTORY_FILE, history)
    write_json(TRACKER_FILE, {"episode": ep_num + 1})

def create_video():
    episode_number = get_next_episode()
    episode_dir = OUTPUT_DIR / f"Episode_{episode_number:03d}"
    episode_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🚀 [Master Engine] Generating Spiritual Episode {episode_number}...")
    content = generate_content_script(episode_number)
    write_json(episode_dir / "script.json", content)
    print("Title:", content["title"])

    for index, scene in enumerate(content["scenes"]):
        print(f"📥 [Image Engine] Downloading scene {index + 1}/{len(content['scenes'])}")
        download_scene_image(scene["image_prompt"], episode_dir / f"scene_{index + 1:02d}.jpg")

    narration_path = episode_dir / "voiceover.mp3"
    print("🎙️ [Voice Engine] Generating neural Hindi voiceover...")
    asyncio.run(generate_audio(content["script"], narration_path))

    print("🎬 [Editing Engine] Rendering cinematic 1080x1920 video with BGM & Subtitles...")
    final_video = render_video(content, episode_dir, episode_number, narration_path)
    
    # 🧠 Strict QA Brain Check (Instant Reject on Failure)
    validate_video(final_video)

    commit_episode(episode_number, content["title"], content["script"])

    metadata = {
        "episode": episode_number,
        "title": content["title"],
        "description": content["description"],
        "hashtags": content.get("hashtags", []),
        "video_file": str(final_video),
        "created_at": datetime.now().isoformat(),
    }

    write_json(episode_dir / "video_metadata.json", metadata)
    shutil.copy(final_video, Path("final_short.mp4"))
    write_json(Path("video_metadata.json"), metadata)

    print("\n✅ [SUCCESS] Video generated, verified by QA Brain, and ready for 1080 upload!")

if __name__ == "__main__":
    try:
        create_video()
    except Exception as error:
        logging.exception("Pipeline failed due to QA rejection or system error")
        print("\n❌ [PIPELINE ERROR / REJECTED]:", error)
        raise error
