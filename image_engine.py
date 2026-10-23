import random
import time
import logging
import urllib.parse
from pathlib import Path
import requests
from PIL import Image, ImageDraw

from config import (
    SHORT_WIDTH, SHORT_HEIGHT, LONG_WIDTH, LONG_HEIGHT, 
    MAX_RETRIES, ASSETS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def create_emergency_fallback(output_path: Path, width: int, height: int, headline_tag: str = "NEWS ALERT"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    default_studio_asset = ASSETS_DIR / "default_studio.jpg"
    if default_studio_asset.exists():
        try:
            with Image.open(default_studio_asset) as img:
                img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
                img_resized.save(output_path, "JPEG", quality=90)
                return output_path
        except Exception:
            pass

    base = Image.new("RGB", (width, height), color=(8, 12, 22))
    draw = ImageDraw.Draw(base)

    for y in range(0, height, 40):
        alpha = int(25 + (y / height) * 35)
        draw.line([(0, y), (width, y)], fill=(alpha, alpha + 15, alpha + 35), width=1)

    box_w, box_h = int(width * 0.75), 100
    x0 = (width - box_w) // 2
    y0 = (height - box_h) // 2
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(180, 20, 20))
    draw.text((x0 + 30, y0 + 35), f"🔴 {headline_tag}", fill=(255, 255, 255))
    base.save(output_path, "JPEG", quality=90)
    return output_path


def download_scene_image(prompt: str, output_path: Path, is_short: bool = True, custom_width: int = None, custom_height: int = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width = custom_width or (SHORT_WIDTH if is_short else LONG_WIDTH)
    height = custom_height or (SHORT_HEIGHT if is_short else LONG_HEIGHT)
    aspect_tag = "vertical 9:16" if is_short else "cinematic horizontal 16:9"

    enhanced_prompt = (
        f"{prompt.strip()}, editorial photojournalism, cinematic studio lighting, "
        f"hyperrealistic 8k broadcast photo, realistic colors, sharp focus, {aspect_tag}, "
        f"news footage still, no watermark, no text overlays"
    )

    encoded_prompt = urllib.parse.quote(enhanced_prompt, safe="")
    seed = random.randint(10000, 9999999)
    
    image_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&seed={seed}&model=flux&nologo=true&enhance=true"
    )

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsStudioAI/2.0"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(image_url, timeout=(15, 60), headers=headers)
            if response.status_code == 200 and len(response.content) > 5000:
                temp_path = output_path.with_suffix(".tmp")
                with open(temp_path, "wb") as f:
                    f.write(response.content)

                with Image.open(temp_path) as img:
                    img_rgb = img.convert("RGB")
                    if img_rgb.size != (width, height):
                        img_rgb = img_rgb.resize((width, height), Image.Resampling.LANCZOS)
                    img_rgb.save(output_path, "JPEG", quality=92)

                if temp_path.exists():
                    temp_path.unlink()

                logging.info(f"✓ Scene image ready: {output_path.name}")
                return output_path
                
        except Exception as e:
            logging.warning(f"Image download retry {attempt}/{MAX_RETRIES} for '{prompt[:30]}...': {e}")
            time.sleep(3)

    logging.error(f"❌ Failed to download image from API. Using studio graphic fallback: {output_path.name}")
    return create_emergency_fallback(output_path, width, height)
