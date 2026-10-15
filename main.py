import os
import json
import random
import time
import requests
from google import genai
import asyncio
import edge_tts
from PIL import Image, ImageDraw
from io import BytesIO
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def generate_story():
    print("🧠 Generating Suspense Story with Gemini...")
    prompt = """
    Create a viral 45-second YouTube Short script about a creepy psychological mystery or internet rule (like 'The 3:14 AM Rule').
    Return ONLY a valid JSON object with no extra markdown or backticks, structured like this:
    {
      "title": "The Creepy 3:14 AM Rule You Should Never Break #shorts",
      "description": "Never look at your phone if you wake up at this exact time...",
      "character_base": "dark moody thriller animation style, volumetric lighting",
      "scenes": [
        "A person waking up in a dark room looking at a glowing phone screen at 3:14 AM",
        "A creepy dark silhouette standing in the bedroom hallway shadows",
        "Close up of a terrified face illuminated by a flickering phone light",
        "A dark shadowy figure reaching out from inside a bedroom mirror"
      ],
      "narration": "Full 45-second script text divided into smooth sentences for voiceover."
    }
    """
    
    models_to_try = ['gemini-3.8-flash', 'gemini-3.0-flash', 'gemini-2.5-pro']
    
    for attempt in range(5):
        for model_name in models_to_try:
            try:
                print(f"Trying {model_name} (Attempt {attempt+1})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()
                return json.loads(text)
            except Exception as e:
                print(f"⚠️ {model_name} busy or unavailable: {e}")
                time.sleep(4)
                
    print("⚠️ Using built-in viral backup story...")
    return {
        "title": "The 3:14 AM Mirror Rule You Must Never Break #shorts",
        "description": "If you wake up at 3:14 AM without an alarm, never look into a mirror...",
        "character_base": "dark moody creepy thriller animation style, volumetric lighting",
        "scenes": [
            "A person waking up suddenly in a dark bedroom looking at a glowing red digital clock showing 3:14 AM",
            "A person walking slowly towards a vintage hallway mirror in the pitch dark shadows",
            "A creepy shadowy reflection in the mirror smiling back in a dark room",
            "A dark bedroom door slowly creaking open by itself in the shadows"
        ],
        "narration": "If you ever wake up at exactly 3:14 AM without an alarm, do not move. According to an old internet rule, your mind is still half-trapped in the dream realm. Whatever you do, never look into a mirror during this minute. Because the reflection staring back at you won't be yours, and once it sees you looking, it knows how to take your place."
    }

async def generate_voice(text):
    print("🎙️ Generating US Voiceover...")
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("voiceover.mp3")

def create_fallback_image(filename):
    img = Image.new('RGB', (1080, 1920), color=(10, 10, 18))
    draw = ImageDraw.Draw(img)
    for y in range(0, 1920, 4):
        shade = int(10 + (y / 1920) * 25)
        draw.line([(0, y), (1080, y)], fill=(shade, 10, shade + 12), width=4)
    img.save(filename, "JPEG")

def generate_images(character_prompt, scenes):
    print("🎨 Generating 3D Visual Scenes...")
    image_files = []
    
    for i, scene in enumerate(scenes):
        filename = f"scene_{i}.jpg"
        # Short, clean prompt so URL never breaks or times out
        clean_prompt = f"{scene}, {character_prompt}, dark horror aesthetic, vertical wallpaper"
        encoded_prompt = requests.utils.quote(clean_prompt[:250])
        
        valid_image = False
        for attempt in range(5):
            seed = random.randint(1000, 999999)
            # Using flux model with unique seed per retry and timeout of 60s
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&seed={seed}&model=flux&nologo=true"
            headers = {
                "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/{random.randint(500,599)}.36"
            }
            try:
                print(f"⏳ Downloading Scene {i+1} (Attempt {attempt+1})...")
                res = requests.get(url, headers=headers, timeout=60)
                if res.status_code == 200 and len(res.content) > 5000:
                    img = Image.open(BytesIO(res.content)).convert("RGB")
                    # Crop out bottom 60px just in case watermark appears, then resize back
                    w, h = img.size
                    img = img.crop((0, 0, w, h - 60)).resize((1080, 1920), Image.LANCZOS)
                    img.save(filename, "JPEG", quality=95)
                    valid_image = True
                    print(f"✅ Scene {i+1} generated successfully!")
                    break
                else:
                    print(f"⚠️ Empty or rate-limited response (status {res.status_code}, size {len(res.content)} bytes)")
            except Exception as e:
                print(f"⚠️ Image {i+1} attempt {attempt+1} error: {e}")
            
            # Wait before retrying so rate-limit resets
            time.sleep(8)
            
        if not valid_image:
            # If still blocked, copy previous valid scene instead of blank purple screen!
            if len(image_files) > 0 and os.path.exists(image_files[-1]):
                print(f"⚠️ Reusing previous scene with zoom effect for scene {i+1}")
                prev_img = Image.open(image_files[-1])
                # Slight zoom-in crop so it looks like a new camera angle!
                w, h = prev_img.size
                zoomed = prev_img.crop((int(w*0.08), int(h*0.08), int(w*0.92), int(h*0.92))).resize((1080, 1920), Image.LANCZOS)
                zoomed.save(filename, "JPEG", quality=95)
            else:
                create_fallback_image(filename)
            
        image_files.append(filename)
        # Cool-down delay between scenes to avoid server block
        time.sleep(6)
        
    return image_files

def create_video(image_files):
    print("🎬 Rendering Video with MoviePy...")
    audio = AudioFileClip("voiceover.mp3")
    duration_per_image = audio.duration / len(image_files)
    
    clips = []
    for img in image_files:
        clip = ImageClip(img).set_duration(duration_per_image)
        clips.append(clip)
        
    video = concatenate_videoclips(clips, method="compose")
    video = video.set_audio(audio)
    video.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    print("✅ Video Successfully Created: final_short.mp4")

if __name__ == "__main__":
    story = generate_story()
    with open("video_metadata.json", "w") as f:
        json.dump(story, f, indent=4)
        
    asyncio.run(generate_voice(story["narration"]))
    img_list = generate_images(story["character_base"], story["scenes"])
    create_video(img_list)
    print("🎉 Pipeline complete!")
