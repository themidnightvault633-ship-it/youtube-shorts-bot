import logging
import json
from pathlib import Path
from config import BASE_DIR, HISTORY_FILE, ASSETS_DIR
from script_engine import generate_content_script
from image_engine import download_scene_image
from voice_engine import generate_scene_voiceover
from video_editor import create_split_screen_video
from moviepy.editor import AudioFileClip, concatenate_audioclips

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    logging.info("🚀 Starting Master AI News Studio...")
    
    episode_number = 1
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                episode_number = len(data.get("episodes", [])) + 1
        except Exception:
            pass

    script_data = generate_content_script(episode_number)
    logging.info(f"📰 Topic Selected: {script_data.get('topic_selected')} [{script_data.get('category')}]")

    scene_data_list = []
    audio_clips = []

    for i, scene in enumerate(script_data["scenes"]):
        img_path = BASE_DIR / f"scene_{i}.png"
        logging.info(f"🎨 Downloading scene {i+1} visual...")
        download_scene_image(scene["image_prompt"], img_path)
        
        scene_audio_path = BASE_DIR / f"voice_{i}.mp3"
        anchor_type = scene.get("anchor", "female_hi" if i % 2 == 0 else "male_hi")
        logging.info(f"🎙️ Generating voice using anchor: {anchor_type}...")
        generate_scene_voiceover(scene["narration"], anchor_type, scene_audio_path)
        
        scene_data_list.append({
            "image_path": img_path,
            "audio_path": scene_audio_path
        })
        audio_clips.append(AudioFileClip(str(scene_audio_path)))

    final_audio_path = BASE_DIR / "voiceover.mp3"
    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(str(final_audio_path), logger=None)
    for ac in audio_clips:
        ac.close()

    output_video = Path("final_short.mp4")
    bg_video = ASSETS_DIR / "background.mp4"
    
    logging.info("🎬 Assembling Viral Split-Screen Short Video...")
    create_split_screen_video(
        scene_data_list, 
        final_audio_path, 
        output_video, 
        background_video_path=bg_video if bg_video.exists() else None
    )
    logging.info(f"✅ Short Video Ready: {output_video}")

    history_data = {"episodes": []}
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            pass
            
    history_data["episodes"].append({
        "episode": episode_number,
        "title": script_data.get("title"),
        "topic": script_data.get("topic_selected"),
        "category": script_data.get("category")
    })
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

    logging.info("🎉 Pipeline completed successfully! Long blueprint saved.")

if __name__ == "__main__":
    main()
