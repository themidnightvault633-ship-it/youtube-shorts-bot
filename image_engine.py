import random
import time
import logging
import urllib.parse
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

from config import (
    SHORT_WIDTH, SHORT_HEIGHT, LONG_WIDTH, LONG_HEIGHT, 
    MAX_RETRIES, ASSETS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Safe resampling filter across all Pillow versions
RESAMPLE_FILTER = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))


def get_safe_font(size: int = 32):
    """Ubuntu / Windows TrueType font load karta hai, warna default fallback."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def ascii_safe(text: str) -> str:
    """Emojis aur non-latin characters hata kar clean ASCII text banata hai taaki PIL crash na ho."""
    return text.encode("ascii", errors="ignore").decode("ascii").strip()


def create_emergency_fallback(output_path: Path, width: int, height: int, headline_tag: str = "BREAKING NEWS"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    default_studio_asset = ASSETS_DIR / "default_studio.jpg"
    if default_studio_asset.exists():
        try:
            with Image.open(default_studio_asset) as img:
                img_resized = img.convert("RGB").resize((width, height), RESAMPLE_FILTER)
                img_resized.save(output_path, "JPEG", quality=90)
                return output_path
        except Exception:
            pass

    base = Image.new("RGB", (width, height), color=(10, 15, 28))
    draw = ImageDraw.Draw(base)

    for y in range(0, height, 40):
        c = int(20 + (y / height) * 30)
        draw.line([(0, y), (width, y)], fill=(c, c + 12, c + 30), width=1)

    box_w, box_h = int(width * 0.75), 110
    x0 = (width - box_w) // 2
    y0 = (height - box_h) // 2
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(190, 20, 30))

    # Emoji ki jagah real graphic live dot draw karein (Zero crash risk)
    dot_r = 12
    dot_x = x0 + 40
    dot_y = y0 + (box_h // 2)
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 255, 255))

    clean_tag = ascii_safe(headline_tag) or "BREAKING NEWS"
    font = get_safe_font(36)
    draw.text((dot_x + 30, y0 + 35), clean_tag, fill=(255, 255, 255), font=font)
    
    base.save(output_path, "JPEG", quality=90)
    return output_path


def download_scene_image(prompt: str, output_path: Path, is_short: bool = True, custom_width: int = None, custom_height: int = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width = custom_width or (SHORT_WIDTH if is_short else LONG_WIDTH)
    height = custom_height or (SHORT_HEIGHT if is_short else LONG_HEIGHT)
    aspect_tag = "vertical 9:16" if is_short else "horizontal 16:9"

    clean_prompt = ascii_safe(prompt)[:220]
    enhanced_prompt = f"{clean_prompt}, photorealistic news broadcast photography, 8k, {aspect_tag}, no text"
    encoded_prompt = urllib.parse.quote(enhanced_prompt, safe="")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsStudioAI/2.0"}

    for attempt in range(1, MAX_RETRIES + 1):
        seed = random.randint(1000, 999999)
        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}&seed={seed}&nologo=true"
        )
        try:
            response = requests.get(image_url, timeout=(20, 90), headers=headers)
            if response.status_code == 200 and len(response.content) > 4000:
                temp_path = output_path.with_suffix(".tmp")
                with open(temp_path, "wb") as f:
                    f.write(response.content)

                with Image.open(temp_path) as img:
                    img_rgb = img.convert("RGB")
                    if img_rgb.size != (width, height):
                        img_rgb = img_rgb.resize((width, height), RESAMPLE_FILTER)
                    img_rgb.save(output_path, "JPEG", quality=92)

                if temp_path.exists():
                    temp_path.unlink()

                logging.info(f"✓ Scene image ready: {output_path.name}")
                return output_path
                
        except Exception as e:
            logging.warning(f"Image download retry {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(4)

    logging.warning(f"⚠️ Using studio graphic fallback for: {output_path.name}")
    return create_emergency_fallback(output_path, width, height)
