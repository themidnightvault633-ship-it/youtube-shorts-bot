import os
import json
import random
import time
import wave
import textwrap
import requests
import numpy as np
from google import genai
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO
from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

VIRAL_STORIES = [
    {
        "title": "Someone Sent Me A Photo Of Myself Sleeping... From Inside My Room #shorts",
        "description": "I live alone on the 14th floor, and my door was locked from the inside...",
        "character_style": "A 22-year-old young man with messy dark hair wearing a dark grey hoodie, cinematic 3D Unreal Engine 5 thriller animation style, dramatic neon blue and warm amber lighting, expressive face, 8k resolution",
        "segments": [
            {
                "narration": "At 2:47 AM, my phone buzzed with an AirDrop request from a device named 'Right Behind You'.",
                "visual": "sitting in bed in a dark apartment looking down at a brightly glowing smartphone screen with a shocked expression, neon blue lighting"
            },
            {
                "narration": "Thinking it was a prank from my neighbor, I clicked accept—and my blood instantly turned to ice.",
                "visual": "extreme close up of terrified wide eyes illuminated by the bright glow of a phone screen in a dark bedroom, sweat on forehead"
            },
            {
                "narration": "It was a high-definition photo of me lying in my bed, taken from the corner of my own ceiling just ten seconds ago.",
                "visual": "high angle POV shot looking down from the ceiling corner at the young man sitting on his bed in a dimly lit apartment bedroom"
            },
            {
                "narration": "I live alone on the fourteenth floor, and my front door was deadbolted from the inside.",
                "visual": "standing up slowly in the bedroom looking towards a heavy locked apartment door with a metal chain lock, tense dramatic shadows"
            },
            {
                "narration": "With my hands shaking, I turned on my phone's flashlight and slowly pointed it toward the open closet door.",
                "visual": "holding up a glowing smartphone flashlight beam cutting through the dark room towards a slightly open wooden closet door"
            },
            {
                "narration": "The closet was empty, but my lock screen lit up with a new text: 'Wrong place to look, check under the bed.'",
                "visual": "two glowing pale eyes staring out from the pitch black gap underneath the bed frame while the boy's feet stand right next to the bed"
            }
        ]
    },
    {
        "title": "Why You Should Never Answer A Call From Your Own Number #shorts",
        "description": "The voice on the other end sounded exactly like me, screaming a warning...",
        "character_style": "A 22-year-old young man with sharp features wearing a red and black jacket, 3D Pixar and Unreal Engine 5 thriller animation style, volumetric cinematic lighting, sharp focus, 8k",
        "segments": [
            {
                "narration": "Two nights ago, my phone started ringing at 3 AM, and the caller ID showed my own name and number.",
                "visual": "standing in a modern kitchen at night holding a ringing smartphone showing an incoming call, dramatic blue moonlight through window"
            },
            {
                "narration": "Every instinct told me to decline it, but curiosity got the better of me and I pressed answer.",
                "visual": "holding the smartphone up to his ear with a tense nervous expression, warm kitchen lamp illuminating half of his face"
            },
            {
                "narration": "Through heavy static, I heard my own voice crying in panic, whispering: 'Do not open the front door at 3:05.'",
                "visual": "wide-eyed horrified reaction while listening to the phone, dark shadows stretching across the wall behind him"
            },
            {
                "narration": "Before I could speak, the line went dead, and the digital clock on my microwave clicked to 3:05 AM.",
                "visual": "looking at a glowing green digital clock on a kitchen microwave showing 3:05 in a dark eerie room"
            },
            {
                "narration": "Suddenly, three loud, desperate knocks echoed from my front door, and someone outside yelled my name in my exact voice.",
                "visual": "standing frozen in the hallway staring at the wooden front door as dust shakes off the frame from a heavy knock"
            },
            {
                "narration": "When I looked through the peephole, I saw myself standing in the hallway—covered in rain, begging to be let in before 'it' found me.",
                "visual": "fisheye peephole view showing an identical twin of the young man outside in a dark corridor looking terrified behind his shoulder"
            }
        ]
    }
]

def generate_story():
    print("🧠 Crafting High-Retention Thriller Story with Gemini...")
    prompt = (
        "Write an ultra-engaging, fast-paced 45-second psychological thriller story for a YouTube Short. "
        "NO boring internet rules. Write a first-person story ('I') with 6 segments: "
        "Segment 1 must be an insane immediate hook in the first 3 seconds. "
        "Segments 2 to 5 must build intense suspense and investigation. "
        "Segment 6 must be a mind-blowing plot twist cliffhanger at the very last second. "
        "Each segment visual MUST describe a completely DIFFERENT camera angle and action. "
        "Return ONLY a valid JSON object with keys: title, description, character_style, and segments "
        "(a list of 6 objects each having narration and visual keys)."
    )
    
    models_to_try = ['gemini-3.8-flash', 'gemini-3.0-flash', 'gemini-2.5-pro']
    
    for attempt in range(3):
        for model_name in models_to_try:
            try:
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
                if "segments" in data and len(data["segments"]) >= 5:
                    print(f"✅ Fresh viral story generated via {model_name}!")
                    return data
            except Exception as e:
                print(f"⚠️ {model_name} unavailable: {e}")
                time.sleep(2)
                
    print("🔥 Using curated High-Retention Viral Thriller Script...")
    return random.choice(VIRAL_STORIES)

def generate_suspense_bgm(duration, filename="bgm.wav"):
    print("🎵 Synthesizing Dark Suspense Background Music & Heartbeat...")
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    
    drone = 0.35 * np.sin(2 * np.pi * 55 * t) + 0.2 * np.sin(2 * np.pi * 110 * t) + 0.12 * np.sin(2 * np.pi * 164.8 * t)
    mod = 0.65 + 0.35 * np.sin(2 * np.pi * 0.2 * t)
    
    beat_cycle = t % 1.2
    thump1 = np.where(beat_cycle < 0.12, np.sin(2 * np.pi * 48 * beat_cycle) * np.exp(-25 * beat_cycle), 0)
    thump2 = np.where((beat_cycle >= 0.22) & (beat_cycle < 0.34), np.sin(2 * np.pi * 42 * (beat_cycle - 0.22)) * np.exp(-30 * (beat_cycle - 0.22)), 0)
    
    audio = (drone * mod + 0.45 * (thump1 + thump2)) * 0.16
    audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
    
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())
    return filename

async def generate_segment_voice(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+8%", pitch="-4Hz")
    await communicate.save(filename)

def draw_subtitles_on_image(img, text):
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except:
        font = ImageFont.load_default()
        
    wrapped_lines = textwrap.wrap(text, width=26)
    y_text = h - 430
    
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_text = (w - line_w) // 2
        
        padding = 14
        draw.rectangle(
            [x_text - padding, y_text - padding, x_text + line_w + padding, y_text + line_h + padding],
            fill=(0, 0, 0)
        )
        for dx, dy in [(-3,-3), (-3,3), (3,-3), (3,3)]:
            draw.text((x_text + dx, y_text + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x_text, y_text), line, font=font, fill=(255, 235, 50))
        y_text += line_h + 30
        
    return img

def fetch_scene_image(character_style, visual_desc, index, base_seed):
    filename = f"scene_{index}.jpg"
    angles = [
        "medium shot", "extreme close-up shot", "high angle wide shot",
        "over-the-shoulder shot", "dramatic low angle shot", "intense close-up shot"
    ]
    angle = angles[index % len(angles)]
    full_prompt = f"{angle}, {visual_desc}, {character_style}, cinematic lighting, ultra detailed"
    encoded_prompt = requests.utils.quote(full_prompt[:270])
    
    models = ["flux", "turbo", "flux", "turbo"]
    
    for attempt in range(4):
        model_choice = models[attempt % len(models)]
        seed = base_seed + (index * 777) + (attempt * 13)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&seed={seed}&model={model_choice}&nologo=true"
        headers = {
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/12{attempt}.0.0.0 Safari/537.36"
        }
        try:
            print(f"🎨 Downloading Unique Scene {index+1} [{model_choice}] (Attempt {attempt+1})...")
            res = requests.get(url, headers=headers, timeout=65)
            if res.status_code == 200 and len(res.content) > 8000:
                img = Image.open(BytesIO(res.content)).convert("RGB")
                w, h = img.size
                img = img.crop((0, 0, w, h - 65)).resize((1080, 1920), Image.LANCZOS)
                img = ImageEnhance.Brightness(img).enhance(1.15)
                img = ImageEnhance.Contrast(img).enhance(1.15)
                img = ImageEnhance.Sharpness(img).enhance(1.3)
                img.save(filename, "JPEG", quality=95)
                print(f"✅ Unique Scene {index+1} saved!")
                return filename
        except Exception as e:
            print(f"⚠️ Scene {index+1} attempt {attempt+1} error: {e}")
        time.sleep(8)
        
    img = Image.new('RGB', (1080, 1920), color=(15, 20, 35))
    img.save(filename, "JPEG")
    return filename

def create_dynamic_clip(image_path, subtitle_text, duration, index):
    base_img = Image.open(image_path).convert("RGB").resize((1080, 1920), Image.LANCZOS)
    zoom_in = (index % 2 == 0)
    
    def make_frame(t):
        progress = t / max(duration, 0.1)
        if zoom_in:
            scale = 1.0 + (0.14 * progress)
        else:
            scale = 1.14 - (0.14 * progress)
            
        new_w, new_h = int(1080 * scale), int(1920 * scale)
        resized = base_img.resize((new_w, new_h), Image.BILINEAR)
        left = (new_w - 1080) // 2
        top = (new_h - 1920) // 2
        cropped = resized.crop((left, top, left + 1080, top + 1920))
        
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
    character_style = story.get("character_style", "3D Unreal Engine 5 thriller animation, dramatic lighting, 8k")
    
    print("🎙️ Generating Fast-Paced Thriller Voiceovers...")
    audio_files = asyncio.run(build_all_voices(segments))
    
    base_seed = random.randint(10000, 80000)
    video_clips = []
    
    for i, seg in enumerate(segments):
        img_file = fetch_scene_image(character_style, seg["visual"], i, base_seed)
        audio_clip = AudioFileClip(audio_files[i])
        
        scene_clip = create_dynamic_clip(img_file, seg["narration"], audio_clip.duration, i)
        scene_clip = scene_clip.set_audio(audio_clip)
        video_clips.append(scene_clip)
        
        if i < len(segments) - 1:
            time.sleep(8)
            
    print("🎬 Combining Scenes & Adding Dark Suspense Background Music...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    
    bgm_file = generate_suspense_bgm(final_video.duration)
    bgm_clip = AudioFileClip(bgm_file)
    mixed_audio = CompositeAudioClip([final_video.audio, bgm_clip])
    final_video = final_video.set_audio(mixed_audio)
    
    final_video.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    print("✅ Viral Thriller Short Ready: final_short.mp4")

if __name__ == "__main__":
    main()
