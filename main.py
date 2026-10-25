import os
import sys
import time
import glob
import argparse
import logging
from datetime import datetime

from config import (
    YT_CLIENT_ID,
    YT_CLIENT_SECRET,
    YT_REFRESH_TOKEN,
    CATEGORIES,
    SHORTS_INTERVAL_HOURS,
    ENABLE_LONG_VIDEOS,
)
from script_engine import generate_news_script
from voice_engine import generate_voice
from image_engine import download_scene_image, download_anchor_studio_image
from video_editor import build_news_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("NewsBot.Main")


def cleanup_temp_files():
    os.makedirs("temp", exist_ok=True)
    for f in glob.glob("temp/*"):
        try:
            os.remove(f)
        except Exception:
            pass


def upload_to_youtube(video_path, script_data, is_short=True):
    """Uploads the rendered Short or Long video directly to YouTube via OAuth2 Refresh Token."""
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        logger.warning("⚠️ YouTube OAuth credentials missing! Video saved locally at: " + video_path)
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials(
            None,
            refresh_token=YT_REFRESH_TOKEN.strip(),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YT_CLIENT_ID.strip(),
            client_secret=YT_CLIENT_SECRET.strip(),
        )
        creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds)

        raw_title = script_data.get("title", "🔴 LIVE Breaking News Update")
        if is_short:
            if "#Shorts" not in raw_title and "#shorts" not in raw_title:
                title = f"{raw_title[:88]} #Shorts"
            else:
                title = raw_title[:100]
        else:
            # For 16:9 Long Video, strip #Shorts so YouTube treats it as a full Long Video
            title = raw_title.replace("#Shorts", "").replace("#shorts", "").strip()[:100]

        description = script_data.get("description", "24x7 Live News Bulletin.")
        if not is_short:
            description = description.replace("#Shorts", "#LongVideo")

        tags = script_data.get("tags", ["Breaking News", "Live News", "Hindi News"])
        if not is_short:
            tags = [t for t in tags if t.lower() != "shorts" and t.lower() != "#shorts"] + ["Special Report", "Full Bulletin"]

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": tags[:15],
                "categoryId": "25",  # News & Politics
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 5, resumable=True, mimetype="video/mp4")
        logger.info(f"📤 Uploading {'SHORT' if is_short else 'LONG VIDEO'} to YouTube: {title[:70]}...")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()

        vid_id = response.get("id")
        logger.info(f"✅ Successfully uploaded to YouTube! Video ID: {vid_id} (https://youtu.be/{vid_id})")
        return vid_id
    except Exception as e:
        logger.error(f"❌ YouTube Upload Failed: {e}")
        return None


def produce_news_episode(category="AUTO", is_short=True, is_breaking=False, anchor_gender=None, skip_upload=False):
    """End-to-end production pipeline for a single BBC / Aaj Tak style broadcast episode (Short or Long)."""
    logger.info("==========================================")
    logger.info(f"🎬 Starting Production: {category} | Format: {'SHORT (9:16)' if is_short else 'LONG (16:9)'} | Breaking: {is_breaking}")
    logger.info("==========================================")

    cleanup_temp_files()
    os.makedirs("output", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    # 1. Generate Broadcast Script (Pure Devanagari Hindi for Nation/Tech, Broadcast English for World)
    script_data = generate_news_script(
        category=category,
        is_short=is_short,
        is_breaking=is_breaking,
        anchor_gender=anchor_gender,
    )
    resolved_cat = script_data.get("category", "NATION")
    language = script_data.get("language", "hindi")
    chosen_gender = script_data.get("anchor_gender", "female")
    scenes = script_data.get("scenes", [])

    logger.info(
        f"📋 Script Ready: '{script_data.get('title')}' | Category: {resolved_cat} | "
        f"Language: {language.upper()} | Anchor: {chosen_gender.upper()} | Scenes: {len(scenes)}"
    )

    # 2. Generate/Fetch Dynamic Male or Female TV News Anchor Studio Portrait
    anchor_img_path = f"temp/anchor_{chosen_gender}_{resolved_cat.lower()}.jpg"
    download_anchor_studio_image(
        anchor_gender=chosen_gender,
        category=resolved_cat,
        output_path=anchor_img_path,
    )

    # 3. Generate Scene Voiceovers & Real Event B-Roll Images
    scene_assets = []
    for idx, scene in enumerate(scenes):
        sid = scene.get("scene_id", idx + 1)
        audio_path = f"temp/voice_{sid}.mp3"
        img_path = f"temp/scene_{sid}.jpg"

        generate_voice(
            text=scene.get("narration", ""),
            output_path=audio_path,
            category=resolved_cat,
            gender=chosen_gender,
            language=language,
        )

        download_scene_image(
            prompt=scene.get("image_prompt", ""),
            output_path=img_path,
            is_short=is_short,
            search_query=scene.get("search_query", ""),
            rss_image_url=scene.get("rss_image_url", ""),
            headline_text=scene.get("headline_banner", ""),
        )

        scene_assets.append({
            "scene_id": sid,
            "audio_path": audio_path,
            "image_path": img_path,
            "narration": scene.get("narration", ""),
            "subtitles": scene.get("subtitles", scene.get("narration", "")),
            "headline_banner": scene.get("headline_banner", script_data.get("headline_banner", "BREAKING NEWS")),
            "camera_angle": scene.get("camera_angle", "closeup" if idx % 2 == 1 else "wide"),
        })

    # 4. Render 30fps Broadcast Video with Audio-Reactive Anchor Motion
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "short" if is_short else "long"
    output_video = f"output/{prefix}_{resolved_cat.lower()}_{timestamp}.mp4"
    build_news_video(
        script_data=script_data,
        scene_assets=scene_assets,
        output_path=output_video,
        is_short=is_short,
        anchor_img_path=anchor_img_path,
    )

    logger.info(f"🎉 Broadcast Video Ready: {output_video}")

    # 5. Upload to YouTube
    if not skip_upload:
        upload_to_youtube(output_video, script_data, is_short=is_short)

    return output_video


def main():
    parser = argparse.ArgumentParser(description="24/7 Autonomous AI TV News Studio Bot")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument(
        "--type",
        choices=["short", "long", "both"],
        default="both",
        help="Video format: 'short' (9:16), 'long' (16:9), or 'both' (uploads 1 Short + 1 Long video)",
    )
    parser.add_argument("--category", default="AUTO", help="NATION, WORLD, TECHNOLOGY, or AUTO")
    parser.add_argument("--anchor", choices=["male", "female", "auto"], default="auto", help="Anchor gender")
    parser.add_argument("--breaking", action="store_true", help="Breaking news mode")
    parser.add_argument("--skip-upload", action="store_true", help="Render locally without YouTube upload")
    args = parser.parse_args()

    anchor_override = None if args.anchor == "auto" else args.anchor

    if args.once:
        if args.type in ("short", "both"):
            produce_news_episode(
                category=args.category,
                is_short=True,
                is_breaking=args.breaking,
                anchor_gender=anchor_override,
                skip_upload=args.skip_upload,
            )
        if args.type in ("long", "both"):
            produce_news_episode(
                category=args.category,
                is_short=False,
                is_breaking=args.breaking,
                anchor_gender=anchor_override,
                skip_upload=args.skip_upload,
            )
        return

    logger.info("📡 Starting 24/7 Autonomous TV News Loop...")
    while True:
        produce_news_episode(category=args.category, is_short=True, is_breaking=False, anchor_gender=anchor_override)
        if ENABLE_LONG_VIDEOS:
            produce_news_episode(category=args.category, is_short=False, is_breaking=False, anchor_gender=anchor_override)
        time.sleep(max(1, SHORTS_INTERVAL_HOURS) * 3600)


if __name__ == "__main__":
    main()
