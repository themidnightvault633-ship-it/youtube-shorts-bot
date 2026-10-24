import asyncio
import time
import logging
from pathlib import Path
import edge_tts
from config import MAX_RETRIES, VOICE_PERSONAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VOICE_MAPPING = {
    "female_hi": "hi-IN-SwaraNeural",
    "male_hi": "hi-IN-MadhurNeural",
    "female_en": "en-US-JennyNeural",
    "male_en": "en-US-GuyNeural",
    "female": "hi-IN-SwaraNeural",
    "male": "hi-IN-MadhurNeural"
}


def resolve_voice_id(anchor_type: str, language: str = "hinglish") -> str:
    anchor_type = anchor_type.lower()
    lang_key = "english" if "en" in anchor_type or language.lower() == "english" else "hinglish"
    gender_key = "female" if "female" in anchor_type else "male"
    
    return VOICE_PERSONAS.get(lang_key, {}).get(gender_key) or VOICE_MAPPING.get(anchor_type, "hi-IN-SwaraNeural")


async def _generate_tts(text: str, voice_id: str, output_audio: Path):
    rate = "+10%" if "hi" in voice_id else "+12%"
    pitch = "-1Hz"
    communicate = edge_tts.Communicate(text=text, voice=voice_id, rate=rate, pitch=pitch)
    await communicate.save(str(output_audio))


def run_async_safe(coroutine):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            return new_loop.run_until_complete(coroutine)
        else:
            return loop.run_until_complete(coroutine)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        return new_loop.run_until_complete(coroutine)


def generate_scene_voiceover(text: str, anchor_type: str, output_path: Path, language: str = "hinglish", **kwargs) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    voice_id = resolve_voice_id(anchor_type, language)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            run_async_safe(_generate_tts(text, voice_id, output_path))
            
            if output_path.exists() and output_path.stat().st_size > 500:
                logging.info(f"✓ Voiceover ready ({voice_id}): {output_path.name}")
                return output_path
        except Exception as e:
            logging.warning(f"Voiceover attempt {attempt}/{MAX_RETRIES} failed ({voice_id}): {e}")
            time.sleep(2)

    raise RuntimeError(f"❌ Voice generation failed for voice: {voice_id}")


def get_audio_duration(audio_path: Path) -> float:
    try:
        try:
            from moviepy.editor import AudioFileClip
        except ImportError:
            from moviepy import AudioFileClip
        clip = AudioFileClip(str(audio_path))
        duration = clip.duration
        clip.close()
        return duration
    except Exception:
        return 5.0
