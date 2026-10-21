import asyncio
import edge_tts
from config import MAX_RETRIES

VOICE = "hi-IN-MadhurNeural"

async def _generate_tts(text, output_path):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate="+12%", pitch="-2Hz")
    await communicate.save(str(output_path))

def generate_voiceover(text, output_path):
    for attempt in range(MAX_RETRIES):
        try:
            asyncio.run(_generate_tts(text, output_path))
            if output_path.exists() and output_path.stat().st_size > 1000:
                return output_path
        except Exception:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError("Voice generation failed!")
    return output_path
