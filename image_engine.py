import math
import random
import time
import logging
import textwrap
import urllib.parse
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

from config import (
    SHORT_WIDTH, SHORT_HEIGHT, LONG_WIDTH, LONG_HEIGHT,
    MAX_RETRIES, ASSETS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESAMPLE_FILTER = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))


def get_safe_font(size: int = 32):
    """Loads TrueType bold font across Ubuntu/Windows, falling back safely."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "arialbd.ttf",
        "arial.ttf"
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def ascii_safe(text: str) -> str:
    """Removes emojis and non-ASCII characters so PIL never crashes."""
    return text.encode("ascii", errors="ignore").decode("ascii").strip()


def create_emergency_fallback(output_path: Path, width: int, height: int, headline_tag: str = "BREAKING NEWS"):
    """
    Creates a rich, bright TV Newsroom Visual Graphic card (with glowing world grid,
    data rings, and wrapped story headline) if external image APIs time out,
    so the screen never looks plain or black.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = Image.new("RGB", (width, height), color=(14, 32, 68))
    draw = ImageDraw.Draw(base)

    cx, cy = width // 2, height // 2
    for y in range(0, height, 4):
        ratio = y / max(1, height)
        r = int(12 + 28 * (1.0 - abs(ratio - 0.45)))
        g = int(38 + 75 * (1.0 - abs(ratio - 0.45)))
        b = int(88 + 135 * (1.0 - abs(ratio - 0.45)))
        draw.rectangle([0, y, width, y + 4], fill=(r, g, b))

    step_x = max(60, width // 14)
    step_y = max(60, height // 12)
    for x in range(0, width, step_x):
        draw.line([(x, 0), (x, height)], fill=(35, 95, 165), width=1)
    for y in range(0, height, step_y):
        draw.line([(0, y), (width, y)], fill=(35, 95, 165), width=1)

    for radius in [int(min(width, height) * r) for r in (0.18, 0.30, 0.42)]:
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=(60, 160, 240),
            width=3
        )

    card_w, card_h = int(width * 0.84), int(height * 0.56)
    x0 = (width - card_w) // 2
    y0 = (height - card_h) // 2
    draw.rectangle([x0, y0, x0 + card_w, y0 + card_h], fill=(10, 24, 52), outline=(0, 195, 255), width=4)

    header_h = 76
    draw.rectangle([x0, y0, x0 + card_w, y0 + header_h], fill=(210, 18, 36))
    dot_r = 11
    dot_x = x0 + 36
    dot_y = y0 + (header_h // 2)
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 255, 255))

    font_header = get_safe_font(32)
    draw.text((dot_x + 26, y0 + 20), "LIVE BROADCAST VISUAL", fill=(255, 255, 255), font=font_header)

    clean_tag = ascii_safe(headline_tag) or "BREAKING NEWS SPECIAL REPORT"
    for junk in ["photorealistic", "8k", "vertical", "9:16", "no text", "no people", "wide-angle", "b-roll"]:
        clean_tag = clean_tag.replace(junk, "").replace(junk.upper(), "").replace(junk.title(), "")
    clean_tag = " ".join(clean_tag.replace(",", " ").split()).strip().upper()
    if len(clean_tag) < 8:
        clean_tag = "INDIA & GLOBAL BREAKING NEWS SPECIAL REPORT"

    wrapped_lines = textwrap.wrap(clean_tag, width=24)[:4]
    font_body = get_safe_font(42)
    text_y = y0 + header_h + 45
    for line in wrapped_lines:
        draw.text((x0 + 42, text_y), line, fill=(255, 255, 255), font=font_body)
        text_y += 62

    base.save(output_path, "JPEG", quality=92)
    return output_path


def download_scene_image(prompt: str, output_path: Path, is_short: bool = True, custom_width: int = None, custom_height: int = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_w = custom_width or (SHORT_WIDTH if is_short else LONG_WIDTH)
    target_h = custom_height or ((SHORT_HEIGHT // 2) if is_short else LONG_HEIGHT)

    req_w = 1024 if is_short else 1280
    req_h = 910 if is_short else 720

    clean_prompt = ascii_safe(prompt)[:200]
    enhanced_prompt = (
        f"{clean_prompt}, dramatic TV news broadcast B-roll photography, "
        f"ultra detailed, vibrant lighting, 8k, no text, no watermark"
    )
    encoded_prompt = urllib.parse.quote(enhanced_prompt, safe="")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
    models = ["flux", "turbo", "flux"]

    for attempt in range(1, MAX_RETRIES + 1):
        seed = random.randint(1000, 999999)
        model_name = models[(attempt - 1) % len(models)]
        cur_w = req_w if attempt <= 2 else (768 if is_short else 960)
        cur_h = req_h if attempt <= 2 else (682 if is_short else 540)

        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={cur_w}&height={cur_h}&seed={seed}&model={model_name}&nologo=true"
        )
        try:
            response = requests.get(image_url, timeout=(15, 45), headers=headers)
            if response.status_code == 200 and len(response.content) > 4000:
                temp_path = output_path.with_suffix(".tmp")
                with open(temp_path, "wb") as f:
                    f.write(response.content)

                with Image.open(temp_path) as img:
                    img_rgb = img.convert("RGB")
                    if img_rgb.size != (target_w, target_h):
                        img_rgb = img_rgb.resize((target_w, target_h), RESAMPLE_FILTER)
                    img_rgb.save(output_path, "JPEG", quality=92)

                if temp_path.exists():
                    temp_path.unlink()

                logging.info(f"✓ Scene B-roll image ready: {output_path.name}")
                return output_path

        except Exception as e:
            logging.warning(f"Image download retry {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(2)

    logging.warning(f"⚠️ Using rich broadcast graphic fallback for: {output_path.name}")
    return create_emergency_fallback(output_path, target_w, target_h, headline_tag=clean_prompt)
