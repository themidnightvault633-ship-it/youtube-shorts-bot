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

# Fix for newer Pillow versions with MoviePy < 2.0
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
      "character_base": "A cinematic dark moody creepy thriller room, 3D Pixar animation style, dramatic volumetric lighting, 8k",
      "scenes": [
        "First sentence scene description visually detailing the hook",
        "Second sentence scene description showing the rising tension",
        "Third sentence scene description showing the creepy twist",
        "Final sentence scene description showing the cliffhanger"
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
        "character_base": "A cinematic dark moody creepy bedroom at night, 3D Pixar animation style, dramatic volumetric lighting, 8k",
        "scenes": [
            "A person waking up suddenly in a dark bedroom looking at a glowing red digital clock showing 3:14 AM",
            "The person walking slowly towards a vintage hallway mirror in the pitch dark shadows",
            "A creepy shadowy reflection in the mirror smiling back while the person looks terrified",
            "The bedroom door slowly creaking open by itself in the dark background"
        ],
        "narration": "If you ever wake up at exactly 3:14 AM without an alarm, do not move. According to an old internet rule, your mind is still half-trapped in the dream realm. Whatever you do, never look into a mirror during this minute. Because the reflection staring back at you won't be yours, and once it sees you looking, it knows how to take your place."
    }

async def generate_voice(text):
    print("🎙️ Generating US Voiceover...")
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("voiceover.mp3")

def create_fallback_image(filename, index):
    # Creates a guaranteed valid 1080x1920 dark atmospheric image if API fails
    img = Image.new('RGB', (1080, 1920), color=(12, 12, 22))
    draw = ImageDraw.Draw(img)
    for y in range(0, 1920, 4):
        shade = int(12 + (y / 1920) * 35)
        draw.line([(0, y), (1080, y)], fill=(shade, 10, shade + 15), width=4)
    img.save(filename, "JPEG")

def generate_images(character_prompt, scenes):
    print("🎨 Generating 3D Visual Scenes...")
    image_files = []
    seed = random.randint(1000, 99999)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for i, scene in enumerate(scenes):
        filename = f"scene_{i}.jpg"
        full_prompt = f"{character_prompt}, {scene}, cinematic lighting"
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(full_prompt)}?width=1080&height=1920&seed={seed+i}&nologo=true"
        
        valid_image = False
        for attempt in range(3):
            try:
                res = requests.get(url, headers=headers, timeout=30)
                if res.status_code == 200 and len(res.content) > 1000:
                    img = Image.open(BytesIO(res.content)).convert("RGB")
                    img.save(filename, "JPEG")
                    valid_image = True
                    print(f"✅ Scene {i+1} downloaded successfully!")
                    break
            except Exception as e:
                print(f"⚠️ Image {i+1} attempt {attempt+1} failed: {e}")
            time.sleep(3)
            
        if not valid_image:
            print(f"⚠️ Using fallback visual for scene {i+1}")
            create_fallback_image(filename, i)
            
        image_files.append(filename)
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
