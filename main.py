import os
import json
import random
import requests
from google import genai
import asyncio
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

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
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt
    )
    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:-3].strip()
    elif text.startswith("```"):
        text = text[3:-3].strip()
    return json.loads(text)

async def generate_voice(text):
    print("🎙️ Generating US Voiceover...")
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("voiceover.mp3")

def generate_images(character_prompt, scenes):
    print("🎨 Generating 3D Visual Scenes...")
    image_files = []
    seed = random.randint(1000, 99999)
    for i, scene in enumerate(scenes):
        full_prompt = f"{character_prompt}, {scene}, cinematic lighting, seed {seed}"
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(full_prompt)}?width=1080&height=1920&nologo=true"
        
        img_data = requests.get(url).content
        filename = f"scene_{i}.jpg"
        with open(filename, "wb") as f:
            f.write(img_data)
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
