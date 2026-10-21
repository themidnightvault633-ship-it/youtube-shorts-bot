import requests
import logging
from pathlib import Path
from PIL import Image
from config import WIDTH, HEIGHT, MAX_RETRIES

def download_scene_image(prompt, output_path):
    # Enforce 3D Pixar & cinematic spiritual rendering tags automatically
    enhanced_prompt = f"{prompt}, 3D Pixar spiritual animation style, highly detailed characters, cinematic divine lighting, 8k resolution, vibrant colors, Unreal Engine 5 render, vertical 9:16"
    encoded_prompt = requests.utils.quote(enhanced_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&enhance=true"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(image_url, timeout=(20, 150), headers={"User-Agent": "SpiritualAIShorts/1.0"})
            response.raise_for_status()

            if not response.headers.get("Content-Type", "").startswith("image/"):
                raise ValueError("Invalid image response type")

            temp_path = output_path.with_suffix(".tmp")
            with open(temp_path, "wb") as file:
                file.write(response.content)

            with Image.open(temp_path) as img:
                img.verify()

            temp_path.replace(output_path)
            return output_path
        except Exception as error:
            logging.exception("Image download failed, retrying...")

    fallback_img = Image.new('RGB', (WIDTH, HEIGHT), color=(15, 10, 30))
    fallback_img.save(output_path)
    return output_path
