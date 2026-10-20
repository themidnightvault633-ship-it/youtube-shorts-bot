import edge_tts
from config import VOICE

async def generate_audio(text, output_path):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate="-2%", pitch="+0Hz")
    await communicate.save(str(output_path))
