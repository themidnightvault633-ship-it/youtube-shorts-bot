import os
import json
import asyncio
import random
import time
import requests
from datetime import datetime
from PIL import Image, ImageDraw

# Pillow compatibility fix for MoviePy
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from google import genai
from google.genai import types
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, TextClip

HISTORY_FILE = "story_history.json"
ANALYTICS_FILE = "performance_metrics.json"

SPIRITUAL_CATEGORIES = [
    "Ramayan Untold Secrets & Divine Lessons",
    "Mahabharat Hidden Truths & Warrior Tales",
    "Lord Shiva & Rudra Mysteries",
    "Ancient Mysterious Indian Temples & Miracles",
    "Garuda Purana & Secrets of Afterlife & Karma",
    "Sanatan Dharma & Vedic Science Wonders"
]

FESTIVALS = [
    {"name": "Ram Navami", "date": "2026-04-06"},
    {"name": "Diwali", "date": "2026-11-08"},
    {"name": "Holi", "date": "2026-03-03"},
    {"name": "Maha Shivratri", "date": "2026-02-15"}
]

def check_upcoming_festival():
    today = datetime.now().date()
    for fest in FESTIVALS:
        fest_date = datetime.strptime(fest["date"], "%Y-%m-%d").date()
        diff = (fest_date - today).days
        if 0 <= diff <= 15:
            return fest["name"], diff
    return None, None

def check_duplicate_story(title):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except:
            pass
    if title in history:
        return True
    history.append(title)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-100:], f)
    return False

def generate_multispiritual_script():
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    fest_name, days_left = check_upcoming_festival()
    
    if fest_name:
        context_prompt = f"Trending Festival Special: The upcoming Hindu festival '{fest_name}' (Coming in {days_left} days). Spiritual significance, rituals, and deep devotion."
    else:
        chosen_category = random.choice(SPIRITUAL_CATEGORIES)
        context_prompt = f"Genre/Category: {chosen_category}. Pick an extremely gripping, emotional, and divine untold story or mystery from this category."

    prompt = f"""
    {context_prompt}
    Act as a top-tier YouTube Shorts viral content creator specializing in Sanatan Dharma, Hindu Mythology, and Spiritual Mysteries.
    Create a highly engaging script optimized for maximum audience retention and high CTR.
    
    Requirements:
    1. A mind-blowing Hook in the first 2 seconds that grabs attention instantly.
    2. Deeply emotional, fact-checked, and devotional storytelling.
    3. Break the script into exactly 3 chronological scenes for visual transitions.
    
    Return ONLY a valid JSON object with these exact keys:
    "title": "A viral catchy title with emojis and relevant hashtags like #shorts #mythology #viral",
    "description": "Engaging description with high-search keywords and hashtags",
    "thumbnail_text": "Short 3-4 words bold text for thumbnail hook",
    "theme": "The core theme of this video",
    "scenes": [
      {{"text": "Hook and beginning part...", "image_prompt": "Cinematic epic visual description for scene 1"}},
      {{"text": "Turning point or deep realization...", "image_prompt": "Cinematic epic visual description for scene 2"}},
      {{"text": "Powerful conclusion and divine lesson...", "image_prompt": "Cinematic epic visual description for scene 3"}}
    ]
    """
    
    for attempt in range(1, 5):
        try:
            print(f"🔄 Trying model gemini-3.8-flash (Attempt {attempt})...")
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(response.text)
            if not check_duplicate_story(data.get("title", "")):
                return data
        except Exception as e:
            print(f"⚠️ Error on attempt {attempt}: {e}")
            if attempt < 4:
                time.sleep(attempt * 5)
            
    return None

async def generate_audio(scenes):
    full_text = " ".join([scene["text"] for scene in scenes])
    print("🎙️ Generating high-quality spiritual voiceover...")
    communicate = edge_tts.Communicate(full_text, "hi-IN-MadhurNeural", rate="+0%", pitch="+0Hz")
    await communicate.save("voiceover.mp3")

def create_video():
    print("🧠 Multi-Spiritual Autonomous Content Engine Running...")
    content = generate_multispiritual_script()
    if not content:
        raise Exception("❌ Failed to generate script after multiple retries due to server load.")
        
    print(f"🎬 Title: {content['title']}")
    print(f"📌 Theme: {content['theme']}")
    
    with open("video_metadata.json", "w") as f:
        json.dump(content, f)
        
    asyncio.run(generate_audio(content["scenes"]))
    
    main_audio = AudioFileClip("voiceover.mp3")
    total_duration = main_audio.duration
    
    scene_clips = []
    scene_duration = total_duration / len(content["scenes"])
    
    for i, scene in enumerate(content["scenes"]):
        print(f"🖼️ Rendering Scene {i+1} visual...")
        img_path = f"scene_{i}.jpg"
        success = False
        
        try:
            img_prompt = f"Divine epic cinematic mythic art, {scene['image_prompt']}, 4k, vertical --ar 9:16"
            encoded_prompt = requests.utils.quote(img_prompt)
            image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
            
            response = requests.get(image_url, timeout=25)
            if response.status_code == 200 and len(response.content) > 1000:
                with open(img_path, "wb") as handler:
                    handler.write(response.content)
                # Verify image can be opened via PIL
                with Image.open(img_path) as test_img:
                    test_img.verify()
                success = True
        except Exception as ex:
            print(f"⚠️ Image download/verify warning for scene {i+1}: {ex}")
            
        # Fallback if image download failed or corrupted
        if not success:
            print(f"⚙️ Using fallback gradient background for Scene {i+1}...")
            img = Image.new('RGB', (1080, 1920), color=(15, 10, 30))
            draw = ImageDraw.Draw(img)
            draw.rectangle([50, 800, 1030, 1120], fill=(30, 20, 50))
            img.save(img_path)
            
        img_clip = ImageClip(img_path).set_duration(scene_duration)
        img_clip = img_clip.resize(lambda t: 1 + 0.04 * t)
        
        txt_clip = TextClip(
            scene["text"], fontsize=38, color='white', font='Arial-Bold',
            size=(950, None), method='caption', stroke_color='black', stroke_width=2
        ).set_duration(scene_duration).set_position(('center', 'center'))
        
        composite_scene = CompositeVideoClip([img_clip, txt_clip])
        scene_clips.append(composite_scene)
        
    print("🎞️ Stitching final master video...")
    final_video = concatenate_videoclips(scene_clips, method="compose")
    final_video = final_video.set_audio(main_audio)
    
    final_video.write_videofile(
        "final_short.mp4", fps=30, codec="libx264", audio_codec="aac", bitrate="5000k"
    )
    print("✅ Multi-Spiritual Cinematic Short successfully created!")

if __name__ == "__main__":
    create_video()
