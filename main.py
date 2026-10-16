import os
import json
import random
import time
import textwrap
import requests
import numpy as np
from google import genai
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def generate_story():
    print("🧠 Generating Sentence-Synced Suspense Story with Gemini...")
    prompt = """
    Create a viral 45-second YouTube Short script about a creepy psychological mystery or urban legend.
    To ensure the character and background look consistent and clear across all scenes, define a specific character and visual style.
    Return ONLY a valid JSON object with no extra markdown or backticks, structured EXACTLY like this with 6 segments:
    {
      "title": "The 3:14 AM Mirror Rule You Must Never Break #shorts",
      "description": "Never look into a mirror if you wake up at this exact time...",
      "character_style": "A 20-year-old boy with messy dark hair wearing a red hoodie, 3D Pixar and Unreal Engine 5 animation style, clear well-lit facial features, bright cyan and warm orange rim lighting, sharp focus, 8k resolution",
      "segments": [
        {
          "narration": "If you ever wake up at exactly 3:14 AM without an alarm, do not get out of bed.",
          "visual": "waking up in a detailed modern bedroom looking at a glowing red digital clock on the nightstand, clear room background"
        },
        {
          "narration": "According to an ancient psychological rule, your mind is still half-trapped in the dream realm.",
          "visual": "sitting on the edge of the bed looking confused and scared, glowing blue moonlight through a large window illuminating the room clearly"
        },
        {
          "narration": "You might hear a faint tapping sound coming from your hallway mirror.",
          "visual": "walking slowly into a well-lit vintage hallway towards a tall ornate mirror on the wall, dramatic shadows"
        },
        {
          "narration": "Whatever you do, never look directly into the glass during this exact minute.",
          "visual": "standing right in front of the glowing vintage mirror, gripping the frame with wide terrified eyes, clear detailed face"
        },
        {
          "narration": "Because the reflection staring back at you will move half a second slower than you do.",
          "visual": "close up of the mirror showing the reflection smiling sinisterly while the real boy looks horrified, bright dramatic lighting"
        },
        {
          "narration": "And once you notice the delay, the reflection knows how to take your place.",
          "visual": "the reflection's hand reaching out through the glowing glass surface of the mirror into the bedroom, ultra detailed cinematic shot"
        }
      ]
    }
    """
    
    models_to_try = ['gemini-3.8-flash', 'gemini-3.0-flash', 'gemini-2.5-pro']
    
    for attempt in range(4):
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
                data = json.loads(text)
                if "segments" in data and len(data["segments"]) > 0:
                    return data
            except Exception as e:
                print(f"⚠️ {model_name} busy: {e}")
                time.sleep(3)
                
    print("⚠️ Using built-in high-definition synced story...")
    return {
        "title": "The 3:14 AM Mirror Rule You Must Never Break #shorts",
        "description": "Never look into a mirror if you wake up at this exact time...",
        "character_style": "A 20-year-old boy with messy dark hair wearing a bright red hoodie, 3D Pixar and Unreal Engine 5 style, clear well-lit face, bright cyan and orange volumetric lighting, sharp focus, 8k",
        "segments": [
            {
                "narration": "If you ever wake up at exactly 3:14 AM without an alarm, do not get out of bed.",
                "visual": "waking up in a detailed bedroom looking at a glowing red digital clock on the nightstand, clear well-lit room background"
            },
            {
                "narration": "According to an old psychological rule, your mind is still half-trapped in the dream realm.",
                "visual": "sitting on the bed looking scared, bright blue moonlight coming through a window illuminating the bedroom clearly"
            },
            {
                "narration": "You might hear a faint tapping sound coming from your hallway mirror.",
                "visual": "walking slowly through a detailed hallway with warm wall lamps towards a tall vintage mirror"
            },
            {
                "narration": "Whatever you do, never look directly into the glass during this exact minute.",
                "visual": "standing in front of the glowing vintage mirror with wide terrified eyes, clear detailed face and background"
            },
            {
                "narration": "Because the reflection staring back at you will move half a second slower than you do.",
                "visual": "close up of the mirror showing the reflection smiling sinisterly while the real boy looks horrified, bright dramatic lighting"
            },
            {
                "narration": "And once you notice the delay, the reflection knows how to take your place.",
                "visual": "the reflection reaching its hand out of the glowing glass mirror into the room, cinematic masterpiece"
            }
        ]
    }

async def generate_segment_voice(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+5%")
    await communicate.save(filename)

def draw_subtitles_on_image(img, text):
    """Draws clean, professional subtitles at the bottom-center of the frame"""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
    except:
        font = ImageFont.load_default()
        
    wrapped_lines = textwrap.wrap(text, width=28)
    y_text = h - 420
    
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_text = (w - line_w) // 2
        
        # Semi-transparent dark pill background behind text for readability
        padding = 14
        draw.rectangle(
            [x_text - padding, y_text - padding, x_text + line_w + padding, y_text + line_h + padding],
            fill=(0, 0, 0)
        )
        # Black stroke outline + Bright Yellow-White text
        for dx, dy in [(-2,-2), (-2,2), (2,-2), (2,2)]:
            draw.text((x_text + dx, y_text + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x_text, y_text), line, font=font, fill=(255, 240, 80))
        y_text += line_h + 28
        
    return img

def fetch_scene_image(character_style, visual_desc, index, base_seed, prev_image_path=None):
    filename = f"scene_{index}.jpg"
    full_prompt = f"{character_style}, {visual_desc}, high contrast, well lit, crystal clear details, vertical 9:16"
    encoded_prompt = requests.utils.quote(full_prompt[:280])
    
    for attempt in range(5):
        seed = base_seed + index + (attempt * 100)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&seed={seed}&model=flux&nologo=true"
        headers = {
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/{random.randint(500,599)}.36"
        }
        try:
            print(f"🎨 Generating HD Scene {index+1} (Attempt {attempt+1})...")
            res = requests.get(url, headers=headers, timeout=60)
            if res.status_code == 200 and len(res.content) > 8000:
                img = Image.open(BytesIO(res.content)).convert("RGB")
                # Remove bottom watermark area & enhance brightness/clarity
                w, h = img.size
                img = img.crop((0, 0, w, h - 65)).resize((1080, 1920), Image.LANCZOS)
                img = ImageEnhance.Brightness(img).enhance(1.18)
                img = ImageEnhance.Contrast(img).enhance(1.12)
                img = ImageEnhance.Sharpness(img).enhance(1.25)
                img.save(filename, "JPEG", quality=95)
                print(f"✅ Scene {index+1} HD image ready!")
                return filename
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
        time.sleep(7)
        
    # Smart fallback if server rate-limits: create a zoomed/flipped variation of previous scene
    if prev_image_path and os.path.exists(prev_image_path):
        print(f"⚠️ Using dynamic camera angle of previous scene for Scene {index+1}")
        img = Image.open(prev_image_path).convert("RGB")
        w, h = img.size
        img = img.crop((int(w*0.1), int(h*0.1), int(w*0.9), int(h*0.9))).resize((1080, 1920), Image.LANCZOS)
        img.save(filename, "JPEG", quality=95)
        return filename
        
    img = Image.new('RGB', (1080, 1920), color=(20, 25, 45))
    img.save(filename, "JPEG")
    return filename

def create_zoom_clip(image_path, subtitle_text, duration):
    """Creates a smooth Ken Burns slow-zoom video clip with burned-in subtitles"""
    base_img = Image.open(image_path).convert("RGB").resize((1080, 1920), Image.LANCZOS)
    
    def make_frame(t):
        # Smoothly zoom in by 12% over the duration of the clip
        progress = t / max(duration, 0.1)
        scale = 1.0 + (0.12 * progress)
        new_w, new_h = int(1080 * scale), int(1920 * scale)
        
        resized = base_img.resize((new_w, new_h), Image.BILINEAR)
        left = (new_w - 1080) // 2
        top = (new_h - 1920) // 2
        cropped = resized.crop((left, top, left + 1080, top + 1920))
        
        # Add crisp subtitle overlay on the frame
        final_frame = draw_subtitles_on_image(cropped, subtitle_text)
        return np.array(final_frame)
        
    clip = ImageClip(np.array(base_img)).set_duration(duration)
    clip = clip.fl(lambda gf, t: make_frame(t))
    return clip

async def build_all_voices(segments):
    audio_files = []
    for i, seg in enumerate(segments):
        aud_file = f"voice_{i}.mp3"
        await generate_segment_voice(seg["narration"], aud_file)
        audio_files.append(aud_file)
    return audio_files

def main():
    story = generate_story()
    with open("video_metadata.json", "w") as f:
        json.dump(story, f, indent=4)
        
    segments = story["segments"]
    character_style = story.get("character_style", "3D Pixar Unreal Engine 5 animation, bright volumetric lighting, clear face, 8k")
    
    print("🎙️ Generating Synced Voiceovers for Each Scene...")
    audio_files = asyncio.run(build_all_voices(segments))
    
    base_seed = random.randint(10000, 99999)
    video_clips = []
    prev_img = None
    
    for i, seg in enumerate(segments):
        img_file = fetch_scene_image(character_style, seg["visual"], i, base_seed, prev_img)
        prev_img = img_file
        
        audio_clip = AudioFileClip(audio_files[i])
        print(f"🎬 Creating animated zoom scene {i+1} (Duration: {audio_clip.duration:.1f}s)...")
        
        scene_clip = create_zoom_clip(img_file, seg["narration"], audio_clip.duration)
        scene_clip = scene_clip.set_audio(audio_clip)
        video_clips.append(scene_clip)
        
        # Cooldown between Pollinations requests so every image downloads cleanly
        if i < len(segments) - 1:
            time.sleep(6)
            
    print("🎬 Rendering Final Synced HD Video...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    final_video.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    print("✅ Pro Video Successfully Created: final_short.mp4")

if __name__ == "__main__":
    main()
