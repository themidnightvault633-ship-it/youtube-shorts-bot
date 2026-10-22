import asyncio
import edge_tts
from config import MAX_RETRIES

ANCHOR_VOICES = {
    "female_hi": "hi-IN-SwaraNeural",
    "male_hi": "hi-IN-MadhurNeural",
    "female_en": "en-US-JennyNeural",
    "male_en": "en-US-GuyNeural"
}

async def _generate_tts(text, voice_id, output_path):
    communicate = edge_tts.Communicate(text=text, voice=voice_id, rate="+12%", pitch="-2Hz")
    await communicate.save(str(output_path))

def generate_scene_voiceover(text, anchor_type, output_path):
    voice_id = ANCHOR_VOICES.get(anchor_type, "hi-IN-SwaraNeural")
    for attempt in range(MAX_RETRIES):
        try:
            asyncio.run(_generate_tts(text, voice_id, output_path))
            if output_path.exists() and output_path.stat().st_size > 500:
                return output_path
        except Exception:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Voice generation failed for anchor {anchor_type}!")
    return output_path
