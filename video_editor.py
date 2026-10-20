import os
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, VideoFileClip, CompositeAudioClip
from config import WIDTH, HEIGHT, FPS, MUSIC_FILE, MUSIC_VOLUME

def find_hindi_font():
    local_font = Path("NotoSansDevanagari-Regular.ttf")
    if local_font.exists():
        return str(local_font)
    try:
        font_url = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
        res = requests.get(font_url, timeout=15)
        if res.status_code == 200:
            with open(local_font, "wb") as f:
                f.write(res.content)
            return str(local_font)
    except Exception:
        pass
    return None

def fit_vertical_image(image_path, episode_number):
    image = Image.open(image_path).convert("RGB")
    source_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT

    if source_ratio > target_ratio:
        new_height = HEIGHT
        new_width = int(new_height * source_ratio)
    else:
        new_width = WIDTH
        new_height = int(new_width / source_ratio)

    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - WIDTH) // 2
    top = (new_height - HEIGHT) // 2
    image = image.crop((left, top, left + WIDTH, top + HEIGHT))
    image = ImageEnhance.Contrast(image).enhance(1.12)
    image = ImageEnhance.Color(image).enhance(1.05)

    draw = ImageDraw.Draw(image)
    font_path = find_hindi_font()
    
    badge_font = ImageFont.truetype(font_path, 42) if font_path else ImageFont.load_default()
    brand_font = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()

    # Episode Badge
    badge_text = f"Spiritual  Episode {episode_number}"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0] + 40
    bh = bbox[3] - bbox[1] + 24
    draw.rounded_rectangle([50, 50, 50 + bw, 50 + bh], radius=10, fill=(212, 175, 55), outline=(255, 255, 255), width=2)
    draw.text((70, 62), badge_text, fill=(20, 20, 20), font=badge_font)

    # Sacred Branding
    brand_text = "॥ ॐ नमः शिवाय ॥"
    bbox_brand = draw.textbbox((0, 0), brand_text, font=brand_font)
    bx_width = bbox_brand[2] - bbox_brand[0]
    draw.text((WIDTH - bx_width - 60, 60), brand_text, fill=(255, 220, 100), font=brand_font, stroke_width=2, stroke_fill=(0, 0, 0))

    return image

def wrap_hindi_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font, stroke_width=2)[2] <= max_width:
            current = test
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def create_subtitle_image(text, output_path):
    font_path = find_hindi_font()
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(font_path, 56) if font_path else ImageFont.load_default()

    lines = wrap_hindi_text(draw, text, font, max_width=920)
    line_height, block_height = 80, 80 * len(lines)
    start_y = HEIGHT - 450 - block_height

    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        y = start_y + index * line_height
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")

    canvas.save(output_path)
    return output_path

def render_video(content, episode_dir, episode_number, narration_path):
    scene_paths = [episode_dir / f"scene_{i + 1:02d}.jpg" for i in range(len(content["scenes"]))]
    final_path = episode_dir / "final_short.mp4"

    audio = AudioFileClip(str(narration_path))
    scene_duration = audio.duration / len(scene_paths)
    clips, subtitle_clips = [], []

    try:
        for index, image_path in enumerate(scene_paths):
            image = fit_vertical_image(image_path, episode_number)
            temp_img_path = episode_dir / f"processed_scene_{index + 1:02d}.jpg"
            image.save(temp_img_path)

            clip = ImageClip(str(temp_img_path)).set_duration(scene_duration).set_position("center")
            clips.append(clip)

            sub_path = episode_dir / f"subtitle_{index + 1:02d}.png"
            create_subtitle_image(content["scenes"][index]["narration"], sub_path)
            sub_clip = ImageClip(str(sub_path), transparent=True).set_duration(scene_duration).set_position(("center", "center"))
            subtitle_clips.append(sub_clip)

        bg_video = concatenate_videoclips(clips, method="compose")
        sub_video = concatenate_videoclips(subtitle_clips, method="compose")
        video = CompositeVideoClip([bg_video, sub_video], size=(WIDTH, HEIGHT)).set_audio(audio)

        final_audio = audio
        if MUSIC_FILE and Path(MUSIC_FILE).is_file():
            try:
                music_clip = AudioFileClip(MUSIC_FILE)
                music_clip = music_clip.audio_loop(duration=audio.duration) if music_clip.duration < audio.duration else music_clip.subclip(0, audio.duration)
                final_audio = CompositeAudioClip([audio, music_clip.volumex(MUSIC_VOLUME)])
            except Exception:
                pass

        video = video.set_audio(final_audio)
        video.write_videofile(str(final_path), fps=FPS, codec="libx264", audio_codec="aac", preset="medium", threads=2, remove_temp=True)

        video.close()
        bg_video.close()
        sub_video.close()
        return final_path
    finally:
        audio.close()
        for c in clips + subtitle_clips:
            try: c.close() except: pass

# ==========================================================
# 🧠 SMART BRAIN / QUALITY ASSURANCE (QA) ENGINE
# ==========================================================
def validate_video(video_path):
    print("🔍 [QA Engine] Running strict quality checks on rendered video...")
    
    if not video_path.exists():
        raise RuntimeError("❌ [QA REJECTED] Final video file does not exist.")
    
    file_size = video_path.stat().st_size
    if file_size < 200_000:
        raise RuntimeError(f"❌ [QA REJECTED] Video file size too small ({file_size} bytes). Possible corruption.")

    clip = VideoFileClip(str(video_path))
    try:
        if clip.w != WIDTH or clip.h != HEIGHT:
            raise RuntimeError(f"❌ [QA REJECTED] Incorrect resolution: {clip.w}x{clip.h}. Required: 1080x1920.")
        
        if clip.duration < 25 or clip.duration > 60:
            raise RuntimeError(f"❌ [QA REJECTED] Invalid video duration: {clip.duration:.2f}s. Must be 35-45s range.")
        
        if clip.audio is None:
            raise RuntimeError("❌ [QA REJECTED] Video has no audio track attached.")
            
        print("✅ [QA PASSED] Video meets all strict 1080x1920 cinematic, audio, and duration standards!")
    finally:
        clip.close()
