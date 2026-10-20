import os
import re
import json
import time
import asyncio
import logging
import random
import shutil
from pathlib import Path
from datetime import datetime

import requests
import edge_tts

from google import genai
from google.genai import types

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    VideoFileClip,
    CompositeAudioClip,
)

# ==========================================================
# CONFIGURATION & SETUP
# ==========================================================

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

BASE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "generation.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing. Add it to your GitHub Secrets.")

client = genai.Client(api_key=API_KEY)

# ==========================================================
# SPIRITUAL CATEGORIES & FESTIVALS AUTOMATION
# ==========================================================

SPIRITUAL_CATEGORIES = [
    "रामायण के अनकहे रहस्य और भगवान राम के चमत्कार",
    "महाभारत के अनसुने सच, श्राप और गुप्त योद्धा गाथाएं",
    "भगवान शिव, रुद्र अवतार और कैलाश पर्वत के रहस्य",
    "प्राचीन रहस्यमयी भारतीय मंदिर और उनके हैरान कर देने वाले चमत्कार",
    "गरुड़ पुराण और परलोक, आत्मा तथा कर्म के भयानक सच",
    "सनातन धर्म, वेद और आधुनिक विज्ञान के अद्भुत आश्चर्य"
]

FESTIVALS = [
    {"name": "Ram Navami", "date": "2026-04-06", "hindi": "राम नवमी विशेष"},
    {"name": "Diwali", "date": "2026-11-08", "hindi": "दीपावली विशेष"},
    {"name": "Holi", "date": "2026-03-03", "hindi": "होली विशेष"},
    {"name": "Maha Shivratri", "date": "2026-02-15", "hindi": "महाशिवरात्रि विशेष"}
]

def check_upcoming_festival():
    today = datetime.now().date()
    for fest in FESTIVALS:
        try:
            fest_date = datetime.strptime(fest["date"], "%Y-%m-%d").date()
            diff = (fest_date - today).days
            if 0 <= diff <= 15:
                return fest["hindi"]
        except:
            pass
    return None

# ==========================================================
# JSON & EPISODE MANAGEMENT (SAFE READ/WRITE)
# ==========================================================

def read_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        logging.exception("Could not read JSON (Corrupt File handled): %s", path)
        return default

def write_json(path, data):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temp_path.replace(path)

def get_next_episode():
    tracker = read_json(TRACKER_FILE, {"episode": 1})
    return max(1, int(tracker.get("episode", 1)))

def commit_episode(episode_number, title, script):
    history = read_json(HISTORY_FILE, {"episodes": []})
    history["episodes"].append({
        "episode": episode_number,
        "title": title,
        "script": script,
        "created_at": datetime.now().isoformat(),
    })
    write_json(HISTORY_FILE, history)
    write_json(TRACKER_FILE, {"episode": episode_number + 1})

# ==========================================================
# AI SCRIPT GENERATOR WITH DUPLICATE CHECKER
# ==========================================================

def generate_content_script(episode_number):
    history = read_json(HISTORY_FILE, {"episodes": []})
    previous_stories = [item.get("title", "") for item in history.get("episodes", [])]

    festival_focus = check_upcoming_festival()
    if festival_focus:
        context_prompt = f"Trending Festival Special: {festival_focus}. Focus on deep devotion, spiritual significance, and divine storytelling."
    else:
        chosen_category = random.choice(SPIRITUAL_CATEGORIES)
        context_prompt = f"Genre / Category: {chosen_category}. Pick an extremely gripping, emotional, and divine untold story from this category."

    prompt = f"""
You are an expert Hindu mythological and spiritual scriptwriter.
Create a short viral vertical YouTube Short episode in pure Shuddh Hindi.

Episode number: {episode_number}
{context_prompt}

Previously used titles (DO NOT REPEAT THESE TOPICS):
{json.dumps(previous_stories[-25:], ensure_ascii=False)}

Requirements:
1. **Hook:** Start with a powerful, attention-grabbing hook in the first 2 seconds.
2. **Language:** Pure Hindi in Devanagari script with respectful devotional tone.
3. **Fact-Check:** Keep facts authentic to Sanatan Dharma traditions and clearly distinguish folklore from established shastric references.
4. **Structure:** Exactly 4 to 5 chronological scenes with setup, main event, and takeaway.
5. **Duration:** Optimized for 35-45 seconds total reading time.

Return ONLY a valid JSON object in this exact structure:
{{
  "title": "Catchy Hindi title with emojis #shorts",
  "description": "SEO-friendly Hindi description with hashtags",
  "script": "Complete Hindi narration text",
  "hashtags": ["#SanatanDharma", "#Bhakti", "#ViralShorts"],
  "scenes": [
    {{
      "narration": "Hindi narration for scene 1",
      "image_prompt": "Detailed cinematic photorealistic visual prompt in English"
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
            required = ["title", "description", "script", "scenes"]

            for key in required:
                if not data.get(key):
                    raise ValueError(f"Missing field: {key}")

            data["scenes"] = data["scenes"][:MAX_SCENES]
            if len(data["scenes"]) < 2:
                raise ValueError("At least 2 scenes are required.")

            scene_script = " ".join(scene["narration"].strip() for scene in data["scenes"])
            data["script"] = scene_script

            if not data.get("hashtags"):
                data["hashtags"] = ["#SanatanDharma", "#Bhakti"]

            return data

        except Exception as error:
            logging.exception("Script generation failed")
            print(f"Script retry {attempt + 1}: {error}")
            time.sleep(2 * (attempt + 1))

    # Safe Fallback Script
    return {
        "title": "रहस्यमयी महादेव और कैलाश पर्वत 🕉️ #shorts",
        "description": "जानिए भगवान शिव से जुड़ा एक अद्भुत और चमत्कारी रहस्य। #sanatan #mahadev",
        "script": "क्या आप जानते हैं कि ब्रह्मांड के रचियता भगवान शिव का निवास कैलाश पर्वत आज भी विज्ञान के लिए एक पहेली है? वैज्ञानिक आज तक यह नहीं समझ पाए कि वहाँ ऐसी कौन सी ऊर्जा है जो समय को भी प्रभावित करती है। पौराणिक कथाओं के अनुसार, यह स्थान साक्षात शिव का धाम है। हर हर महादेव!",
        "hashtags": ["#Mahadev", "#Shiva", "#SanatanDharma"],
        "scenes": [
            {"narration": "क्या आप जानते हैं कि ब्रह्मांड के रचियता भगवान शिव का निवास कैलाश पर्वत आज भी विज्ञान के लिए एक पहेली है?", "image_prompt": "Majestic Mount Kailash under cosmic sky, cinematic divine lighting, 4k vertical"},
            {"narration": "वैज्ञानिक आज तक यह नहीं समझ पाए कि वहाँ ऐसी कौन सी ऊर्जा है जो समय को भी प्रभावित करती है।", "image_prompt": "Mystical fog and glowing aura over snowy Himalayan peaks, dramatic cinematic lighting"},
            {"narration": "पौराणिक कथाओं के अनुसार, यह स्थान साक्षात शिव का धाम है। हर हर महादेव!", "image_prompt": "Divine silhouette of Lord Shiva meditating with cosmic energy rays, epic art"}
        ]
    }

# ==========================================================
# AUDIO & VOICE GENERATION
# ==========================================================

async def generate_audio(text, output_path):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate="-2%", pitch="+0Hz")
    await communicate.save(str(output_path))

# ==========================================================
# AI IMAGE GENERATOR (RETRY & VALIDATION)
# ==========================================================

def download_scene_image(prompt, output_path):
    enhanced_prompt = f"{prompt}, highly detailed, cinematic lighting, 8k resolution, photorealistic, Unreal Engine 5 render"
    encoded_prompt = requests.utils.quote(enhanced_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&enhance=true"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(image_url, timeout=(20, 150), headers={"User-Agent": "SpiritualAIShorts/1.0"})
            response.raise_for_status()

            if not response.headers.get("Content-Type", "").startswith("image/"):
                raise ValueError("Expected image response")

            temp_path = output_path.with_suffix(".tmp")
            with open(temp_path, "wb") as file:
                file.write(response.content)

            with Image.open(temp_path) as image:
                image.verify()

            temp_path.replace(output_path)
            return output_path

        except Exception as error:
            logging.exception("Image download failed")
            print(f"Image retry {attempt + 1}: {error}")
            time.sleep(2 * (attempt + 1))

    # Fallback image if download completely fails
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(15, 10, 30))
    img.save(output_path)
    return output_path

# ==========================================================
# HINDI FONT & SUBTITLE SYSTEM
# ==========================================================

def find_hindi_font():
    local_font = Path("NotoSansDevanagari-Regular.ttf")
    if local_font.exists():
        return str(local_font)
    
    try:
        font_url = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
        res = requests.get(font_url, timeout=15)
        if res.status_code == 200:
            with open(local_font, "wb") as f:
                f.write(res.content)
            return str(local_font)
    except Exception as e:
        print(f"⚠️ Font download warning: {e}")

    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "C:/Windows/Fonts/NirmalaB.ttf",
        "C:/Windows/Fonts/mangal.ttf",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None

def fit_vertical_image(image_path, episode_number):
    image = Image.open(image_path).convert("RGB")
    source_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT

    if source_ratio > target_ratio:
        new_height = HEIGHT
        new_width = int(new_height * source_ratio)
    else:
        new_width = WIDTH
        new_height = int(new_width / source_ratio)

    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - WIDTH) // 2
    top = (new_height - HEIGHT) // 2
    image = image.crop((left, top, left + WIDTH, top + HEIGHT))
    image = ImageEnhance.Contrast(image).enhance(1.1)

    draw = ImageDraw.Draw(image)
    font_path = find_hindi_font()
    
    badge_font = ImageFont.truetype(font_path, 42) if font_path else ImageFont.load_default()
    brand_font = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()

    # Episode Badge (Top Left)
    badge_text = f"Spiritual  Episode {episode_number}"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0] + 40
    bh = bbox[3] - bbox[1] + 24
    draw.rounded_rectangle([50, 50, 50 + bw, 50 + bh], radius=10, fill=(212, 175, 55), outline=(255, 255, 255), width=2)
    draw.text((70, 62), badge_text, fill=(20, 20, 20), font=badge_font)

    # Sacred Branding (Top Right)
    brand_text = "॥ ॐ नमः शिवाय ॥"
    bbox_brand = draw.textbbox((0, 0), brand_text, font=brand_font)
    bx_width = bbox_brand[2] - bbox_brand[0]
    draw.text((WIDTH - bx_width - 60, 60), brand_text, fill=(255, 220, 100), font=brand_font, stroke_width=2, stroke_fill=(0, 0, 0))

    return image

def wrap_hindi_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), test, font=font, stroke_width=2)[2]
        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def create_subtitle_image(text, output_path):
    font_path = find_hindi_font()
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(font_path, 56) if font_path else ImageFont.load_default()

    lines = wrap_hindi_text(draw, text, font, max_width=920)
    line_height = 80
    block_height = line_height * len(lines)
    start_y = HEIGHT - 450 - block_height

    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        text_width = bbox[2] - bbox[0]
        x = (WIDTH - text_width) // 2
        y = start_y + index * line_height
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")

    canvas.save(output_path)
    return output_path

# ==========================================================
# CINEMATIC VIDEO RENDERING & QUALITY CHECKER
# ==========================================================

def render_video(content, episode_dir, episode_number):
    scene_paths = [episode_dir / f"scene_{i + 1:02d}.jpg" for i in range(len(content["scenes"]))]
    narration_path = episode_dir / "voiceover.mp3"
    final_path = episode_dir / "final_short.mp4"

    asyncio.run(generate_audio(content["script"], narration_path))

    audio = AudioFileClip(str(narration_path))
    total_duration = audio.duration

    if not total_duration or total_duration <= 0:
        audio.close()
        raise RuntimeError("Voiceover duration is invalid.")

    scene_duration = total_duration / len(scene_paths)
    clips = []
    subtitle_clips = []

    try:
        for index, image_path in enumerate(scene_paths):
            image = fit_vertical_image(image_path, episode_number)
            temp_img_path = episode_dir / f"processed_scene_{index + 1:02d}.jpg"
            image.save(temp_img_path)

            clip = ImageClip(str(temp_img_path)).set_duration(scene_duration).set_position("center")
            clips.append(clip)

            subtitle_path = episode_dir / f"subtitle_{index + 1:02d}.png"
            create_subtitle_image(content["scenes"][index]["narration"], subtitle_path)

            subtitle_clip = ImageClip(str(subtitle_path), transparent=True).set_duration(scene_duration).set_position(("center", "center"))
            subtitle_clips.append(subtitle_clip)

        background_video = concatenate_videoclips(clips, method="compose")
        subtitle_video = concatenate_videoclips(subtitle_clips, method="compose")

        video = CompositeVideoClip([background_video, subtitle_video], size=(WIDTH, HEIGHT)).set_audio(audio)

        # Background Music Integration
        final_audio = audio
        if MUSIC_FILE and Path(MUSIC_FILE).is_file():
            try:
                music_clip = AudioFileClip(MUSIC_FILE)
                if music_clip.duration < total_duration:
                    music_clip = music_clip.audio_loop(duration=total_duration)
                else:
                    music_clip = music_clip.subclip(0, total_duration)
                music_clip = music_clip.volumex(MUSIC_VOLUME)
                final_audio = CompositeAudioClip([audio, music_clip])
            except Exception as e:
                print(f"⚠️ BGM loading warning: {e}")

        video = video.set_audio(final_audio)

        video.write_videofile(
            str(final_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            temp_audiofile=str(episode_dir / "temp_audio.m4a"),
            remove_temp=True,
        )

        video.close()
        background_video.close()
        subtitle_video.close()
        return final_path

    finally:
        audio.close()
        for clip in clips + subtitle_clips:
            try:
                clip.close()
            except Exception:
                pass

def validate_video(video_path):
    if not video_path.exists():
        raise RuntimeError("Final video file was not created.")
    if video_path.stat().st_size < 100_000:
        raise RuntimeError("Video file is unexpectedly small.")

    clip = VideoFileClip(str(video_path))
    try:
        if clip.w != WIDTH or clip.h != HEIGHT:
            raise RuntimeError(f"Wrong resolution: {clip.w}x{clip.h}")
        if clip.duration <= 1:
            raise RuntimeError("Video duration is too short.")
        if clip.audio is None:
            raise RuntimeError("Video has no audio.")
    finally:
        clip.close()

# ==========================================================
# MAIN PIPELINE EXECUTION
# ==========================================================

def create_video():
    episode_number = get_next_episode()
    episode_dir = OUTPUT_DIR / f"Episode_{episode_number:03d}"
    episode_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating Spiritual Episode {episode_number}...")
    content = generate_content_script(episode_number)

    write_json(episode_dir / "script.json", content)
    print("Title:", content["title"])

    for index, scene in enumerate(content["scenes"]):
        print(f"Downloading scene {index + 1}/{len(content['scenes'])}")
        image_path = episode_dir / f"scene_{index + 1:02d}.jpg"
        download_scene_image(scene["image_prompt"], image_path)

    final_video = render_video(content, episode_dir, episode_number)
    validate_video(final_video)

    # Commit episode ONLY after successful validation
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
    
    # Copy to root for automated YouTube upload pipeline
    shutil.copy(final_video, Path("final_short.mp4"))
    write_json(Path("video_metadata.json"), metadata)

    print("\nSUCCESS! Video generated and validated successfully.")

if __name__ == "__main__":
    try:
        create_video()
    except Exception as error:
        logging.exception("Pipeline failed")
        print("\nERROR:", error)
        # Safe Fallback to ensure upload script never blocks workflow
        fallback_meta = {
            "title": "रहस्यमयी महादेव 🕉️ #shorts",
            "description": "जानिए भगवान शिव से जुड़ा रहस्य। #sanatan #mahadev #shorts",
            "hashtags": ["#shorts", "#mahadev"]
        }
        write_json(Path("video_metadata.json"), fallback_meta)
        if not Path("final_short.mp4").exists() and Path("Spiritual_AI_Video/output/Episode_001/final_short.mp4").exists():
            shutil.copy(Path("Spiritual_AI_Video/output/Episode_001/final_short.mp4"), Path("final_short.mp4"))
        raise error
