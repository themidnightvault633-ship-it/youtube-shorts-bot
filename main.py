import os
import sys
import time
import json
import logging
import random
import argparse
from datetime import datetime
from pathlib import Path

from config import (
    BASE_DIR, HISTORY_FILE, ASSETS_DIR, SHORTS_DIR, LONG_DIR,
    SCHEDULE_MORNING_TIME, SCHEDULE_EVENING_TIME,
    MONITOR_CHECK_INTERVAL_SECONDS
)

from script_engine import generate_content_script, fetch_live_news_by_category
from image_engine import download_scene_image
from voice_engine import generate_scene_voiceover
from video_editor import create_split_screen_video, create_long_video

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_PICKLE_FILE = "token.pickle"
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


def get_youtube_service():
    credentials = None
    if os.path.exists(TOKEN_PICKLE_FILE):
        try:
            with open(TOKEN_PICKLE_FILE, "rb") as token:
                credentials = pickle.load(token)
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                logging.warning("⚠️ client_secrets.json missing hai. YouTube upload skip ho jayega.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_UPLOAD_SCOPE)
            credentials = flow.run_local_server(port=0)

        with open(TOKEN_PICKLE_FILE, "wb") as token:
            pickle.dump(credentials, token)

    return build("youtube", "v3", credentials=credentials)


def upload_to_youtube(video_path: Path, title: str, description: str, tags: list, is_short: bool = True):
    youtube = get_youtube_service()
    if not youtube:
        logging.warning("YouTube service unavailable. Skipping cloud upload.")
        return None

    try:
        logging.info(f"📤 Uploading to YouTube: {title}")
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "25"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(str(video_path), chunksize=1024 * 1024 * 5, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logging.info(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        logging.info(f"🎉 LIVE on YouTube: https://youtu.be/{video_id}")
        return video_id
    except Exception as e:
        logging.error(f"❌ YouTube upload failed: {e}")
        return None


def produce_news_episode(category=None, video_type="short", force_anchor=None, is_breaking=False):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ep_dir = BASE_DIR / f"run_{timestamp}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    logging.info(f"\n{'='*50}\n🎬 Starting Production: {category or 'AUTO'} | Format: {video_type.upper()} | Breaking: {is_breaking}\n{'='*50}")

    script_data = generate_content_script(
        forced_category="BREAKING" if is_breaking else category,
        force_anchor_gender=force_anchor
    )
    
    topic = script_data.get("topic_selected")
    cat = script_data.get("category")
    anchor_gender = script_data.get("anchor_gender", "female")
    lang = script_data.get("language", "Hinglish")
    logging.info(f"📰 Topic: {topic} | Anchor: {anchor_gender.upper()} | Language: {lang}")

    anchor_type = f"{anchor_gender}_hi" if "hinglish" in lang.lower() or "hindi" in lang.lower() else f"{anchor_gender}_en"

    scene_data_list = []
    is_short = (video_type == "short")

    for i, scene in enumerate(script_data["scenes"]):
        img_path = ep_dir / f"scene_{i}.jpg"
        logging.info(f"🎨 Visual {i+1}/4: Generating...")
        download_scene_image(scene["image_prompt"], img_path, is_short=is_short)

        aud_path = ep_dir / f"voice_{i}.mp3"
        logging.info(f"🎙️ Audio {i+1}/4: Voiceover with {anchor_type}...")
        generate_scene_voiceover(scene["narration"], anchor_type, aud_path, language=lang)

        scene_data_list.append({
            "image_path": img_path,
            "audio_path": aud_path
        })

    anchor_video = ASSETS_DIR / "anchor_studio.mp4"
    if not anchor_video.exists():
        user_uploaded = Path("user_uploaded_files/ttl=63d/user_uploaded/1000121747.mp4")
        if user_uploaded.exists():
            anchor_video = user_uploaded

    if is_short:
        output_video = SHORTS_DIR / f"Short_{timestamp}.mp4"
        logging.info("✂️ Assembling 9:16 Split-Screen Short with TV Breaking Banner...")
        create_split_screen_video(
            scene_data_list=scene_data_list,
            output_path=output_video,
            video_title=script_data.get("title"),
            is_breaking=is_breaking,
            anchor_video_path=anchor_video if anchor_video.exists() else None
        )
    else:
        output_video = LONG_DIR / f"Long_{timestamp}.mp4"
        logging.info("📺 Assembling 16:9 In-Depth News Feature Video...")
        create_long_video(
            scene_data_list=scene_data_list,
            output_path=output_video,
            video_title=script_data.get("title")
        )

    metadata = {
        "file": str(output_video),
        "title": script_data.get("title"),
        "description": script_data.get("description", "") + "\n\n" + " ".join(script_data.get("hashtags", [])),
        "tags": script_data.get("hashtags", ["News", "Trending", "BreakingNews"]),
        "category": cat,
        "format": video_type,
        "timestamp": timestamp
    }
    with open(ep_dir / "video_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    upload_to_youtube(
        video_path=output_video,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        is_short=is_short
    )

    history_data = {"episodes": []}
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            pass

    history_data["episodes"].append({
        "timestamp": timestamp,
        "title": script_data.get("title"),
        "topic": topic,
        "category": cat,
        "format": video_type,
        "is_breaking": is_breaking
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

    logging.info(f"✅ Production Finished: {output_video.name}\n")
    return output_video


def run_247_autonomous_daemon():
    logging.info("🌐 24/7 Autonomous News Studio Daemon Activated! Monitoring live feeds...")
    last_morning_date = None
    last_evening_date = None
    processed_breaking_titles = set()

    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")

            all_news = fetch_live_news_by_category()
            breaking_list = all_news.get("BREAKING", [])

            for b in breaking_list:
                b_title = b["title"]
                if b_title not in processed_breaking_titles:
                    logging.info(f"🚨🚨 BREAKING NEWS DETECTED: {b_title}")
                    processed_breaking_titles.add(b_title)
                    
                    produce_news_episode(
                        category="BREAKING",
                        video_type="short",
                        force_anchor=random.choice(["female", "male"]),
                        is_breaking=True
                    )
                    break

            if current_time == SCHEDULE_MORNING_TIME and last_morning_date != current_date:
                logging.info("☀️ Morning Schedule Triggered! Creating Morning Digest (Short + Long)...")
                produce_news_episode(category="NATION", video_type="short", force_anchor="female")
                produce_news_episode(category="TECHNOLOGY", video_type="long", force_anchor="male")
                last_morning_date = current_date

            elif current_time == SCHEDULE_EVENING_TIME and last_evening_date != current_date:
                logging.info("🌙 Evening Schedule Triggered! Creating Evening Roundup (Short + Long)...")
                produce_news_episode(category="WORLD", video_type="short", force_anchor="male")
                produce_news_episode(category="NATION", video_type="long", force_anchor="female")
                last_evening_date = current_date

            time.sleep(MONITOR_CHECK_INTERVAL_SECONDS)

        except Exception as e:
            logging.error(f"Error in 24/7 monitor loop: {e}")
            time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous AI News Studio")
    parser.add_argument("--daemon", action="store_true", help="24/7 background automation loop run karein")
    parser.add_argument("--once", action="store_true", help="Ek single episode turant render karein")
    parser.add_argument("--type", choices=["short", "long"], default="short", help="Video format")
    parser.add_argument("--category", choices=["NATION", "WORLD", "TECHNOLOGY", "BREAKING"], default=None)
    parser.add_argument("--anchor", choices=["male", "female"], default=None)

    args = parser.parse_args()

    if args.daemon:
        run_247_autonomous_daemon()
    else:
        produce_news_episode(
            category=args.category,
            video_type=args.type,
            force_anchor=args.anchor,
            is_breaking=(args.category == "BREAKING")
        )
