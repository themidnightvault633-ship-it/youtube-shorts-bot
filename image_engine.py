import random
import requests
import time
import logging
from PIL import Image
from config import WIDTH, HEIGHT, MAX_RETRIES

def download_scene_image(prompt, output_path):
    seed = random.randint(1000, 999999)
    enhanced_prompt = f"{prompt}, photorealistic documentary news illustration, cinematic dark lighting, 8k resolution, vertical 9:16, no text"
    encoded_prompt = requests.utils.quote(enhanced_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={WIDTH}&height={HEIGHT}&seed={seed}&nologo=true&enhance=true"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(image_url, timeout=(20, 120), headers={"User-Agent": "NewsAI/1.0"})
            response.raise_for_status()

            temp_path = output_path.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                f.write(response.content)

            with Image.open(temp_path) as img:
                img.verify()

            temp_path.replace(output_path)
            return output_path
        except Exception:
            logging.warning(f"Image download retry {attempt}")
            time.sleep(3)

    fallback = Image.new("RGB", (WIDTH, HEIGHT), color=(10, 15, 25))
    fallback.save(output_path)
    return output_path
