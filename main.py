import logging
from pathlib import Path
from config import BASE_DIR, HISTORY_FILE, LONG_SCRIPT_FILE
from script_engine import generate_content_script
from image_engine import download_scene_image
from voice_engine import generate_voiceover
from video_editor import create_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    logging.info("🚀 Starting Tech & Geopolitics News Automated Studio...")
    
    # 1. Generate Script & Long Blueprint
    episode_number = 1
    if HISTORY_FILE.exists():
        try:
            import json
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                episode_number = len(data.get("episodes", [])) + 1
        except Exception:
            pass

    script_data = generate_content_script(episode_number)
    logging.info(f"📰 Topic Selected: {script_data.get('topic_selected')}")

    # 2. Download Scene Images
    image_paths = []
    for i, scene in enumerate(script_data["scenes"]):
        img_path = BASE_DIR / f"scene_{i}.png"
        logging.info(f"🎨 Downloading image {i+1}/4...")
        download_scene_image(scene["image_prompt"], img_path)
        image_paths.append(img_path)

    # 3. Generate Voiceover
    audio_path = BASE_DIR / "voiceover.mp3"
    logging.info("🎙️ Generating professional news voiceover...")
    generate_voiceover(script_data["script"], audio_path)

    # 4. Create Final Short Video
    output_video = Path("final_short.mp4")
    logging.info("🎬 Assembling 1080p Full HD Short Video...")
    create_video(image_paths, audio_path, output_video)
    logging.info(f"✅ Short Video Ready: {output_video}")

    # 5. Save History
    history_data = {"episodes": []}
    if HISTORY_FILE.exists():
        try:
            import json
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            pass
            
    history_data["episodes"].append({
        "episode": episode_number,
        "title": script_data.get("title"),
        "topic": script_data.get("topic_selected")
    })
    
    import json
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

    logging.info("🎉 Pipeline completed successfully! Long script saved to Tech_News_AI_Studio/")

if __name__ == "__main__":
    main()
