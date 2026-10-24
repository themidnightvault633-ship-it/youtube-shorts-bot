import logging
from pathlib import Path

# ================= PILLOW ANTIALIAS COMPATIBILITY PATCH =================
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, 'LANCZOS', PIL.Image.BICUBIC)
if not hasattr(PIL.Image, 'LANCZOS'):
    PIL.Image.LANCZOS = PIL.Image.BICUBIC
# ========================================================================

from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import (
    ImageClip, VideoFileClip, AudioFileClip, 
    concatenate_videoclips, clips_array, ColorClip, 
    CompositeVideoClip, concatenate_audioclips
)

from config import (
    SHORT_WIDTH, SHORT_HEIGHT, LONG_WIDTH, LONG_HEIGHT, 
    FPS, ASSETS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_safe_font(size: int = 28):
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
    """Removes emojis and non-ASCII characters so PIL ImageDraw never throws latin-1 error."""
    return text.encode("ascii", errors="ignore").decode("ascii").strip()


def create_breaking_news_banner(width: int, height: int, title_text: str, is_breaking: bool = False) -> str:
    banner_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(banner_img)
    font = get_safe_font(28)

    tag_w = 270
    tag_bg = (220, 20, 60, 255) if is_breaking else (185, 10, 20, 255)
    draw.rectangle([0, 0, tag_w, height], fill=tag_bg)

    # Emoji ki jagah real graphic white circle
    dot_r = 9
    dot_x = 28
    dot_y = height // 2
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 255, 255))

    label_text = "BREAKING" if is_breaking else "TOP NEWS"
    draw.text((dot_x + 20, height // 2 - 16), label_text, fill=(255, 255, 255), font=font)

    # Dark headline bar
    draw.rectangle([tag_w, 0, width, height], fill=(12, 18, 30, 240))
    
    clean_title = ascii_safe(title_text.replace("#Shorts", "").replace("#shorts", ""))
    if not clean_title:
        clean_title = "LATEST HEADLINE UPDATE"
    if len(clean_title) > 42:
        clean_title = clean_title[:39] + "..."
    draw.text((tag_w + 25, height // 2 - 16), clean_title, fill=(255, 255, 255), font=font)

    temp_banner_path = ASSETS_DIR / "temp_banner.png"
    banner_img.save(temp_banner_path, "PNG")
    return str(temp_banner_path)


def create_split_screen_video(scene_data_list, output_path, video_title="NEWS UPDATE", is_breaking=False, anchor_video_path=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_allocated_clips = []

    try:
        top_height = SHORT_HEIGHT // 2
        bottom_height = SHORT_HEIGHT - top_height

        top_clips = []
        audio_clips = []

        for item in scene_data_list:
            img_path = item["image_path"]
            aud_path = item["audio_path"]

            s_audio = AudioFileClip(str(aud_path))
            scene_duration = s_audio.duration
            audio_clips.append(s_audio)
            all_allocated_clips.append(s_audio)

            img_clip = ImageClip(str(img_path)).set_duration(scene_duration)
            img_clip = img_clip.resize(width=SHORT_WIDTH)
            if img_clip.h > top_height:
                img_clip = img_clip.crop(x1=0, y1=(img_clip.h - top_height) / 2, x2=SHORT_WIDTH, y2=(img_clip.h + top_height) / 2)
            elif img_clip.h < top_height:
                img_clip = img_clip.resize(height=top_height)
            
            top_clips.append(img_clip)
            all_allocated_clips.append(img_clip)

        final_audio = concatenate_audioclips(audio_clips)
        top_final = concatenate_videoclips(top_clips, method="compose")
        total_duration = final_audio.duration
        all_allocated_clips.extend([final_audio, top_final])

        anchor_path = anchor_video_path or (ASSETS_DIR / "anchor_studio.mp4")
        if not Path(anchor_path).exists():
            candidate = Path("user_uploaded_files/ttl=63d/user_uploaded/1000121747.mp4")
            if candidate.exists():
                anchor_path = candidate

        if Path(anchor_path).exists():
            bottom_clip = VideoFileClip(str(anchor_path)).without_audio()
            if bottom_clip.duration < total_duration:
                bottom_clip = bottom_clip.loop(duration=total_duration)
            else:
                bottom_clip = bottom_clip.subclip(0, total_duration)

            bottom_clip = bottom_clip.resize(height=bottom_height)
            if bottom_clip.w > SHORT_WIDTH:
                bottom_clip = bottom_clip.crop(x1=(bottom_clip.w - SHORT_WIDTH) / 2, y1=0, x2=(bottom_clip.w + SHORT_WIDTH) / 2, y2=bottom_height)
        else:
            bottom_clip = ColorClip(size=(SHORT_WIDTH, bottom_height), color=(14, 20, 32)).set_duration(total_duration)

        all_allocated_clips.append(bottom_clip)

        split_layout = clips_array([[top_final], [bottom_clip]])
        all_allocated_clips.append(split_layout)

        banner_h = 90
        banner_file = create_breaking_news_banner(SHORT_WIDTH, banner_h, video_title, is_breaking)
        banner_clip = ImageClip(banner_file).set_duration(total_duration).set_pos((0, top_height - (banner_h // 2)))
        all_allocated_clips.append(banner_clip)

        final_composite = CompositeVideoClip([split_layout, banner_clip], size=(SHORT_WIDTH, SHORT_HEIGHT))
        final_video = final_composite.set_audio(final_audio)
        all_allocated_clips.extend([final_composite, final_video])

        final_video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="6000k",
            preset="ultrafast",
            threads=4,
            logger=None
        )

        logging.info(f"✓ Split-Screen Short ready: {output_path.name}")
        return output_path

    finally:
        for c in all_allocated_clips:
            try:
                c.close()
            except Exception:
                pass


def create_long_video(scene_data_list, output_path, video_title="SPECIAL REPORT"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_allocated_clips = []

    try:
        video_clips = []
        audio_clips = []

        for item in scene_data_list:
            img_path = item["image_path"]
            aud_path = item["audio_path"]

            s_audio = AudioFileClip(str(aud_path))
            scene_duration = s_audio.duration
            audio_clips.append(s_audio)
            all_allocated_clips.append(s_audio)

            img_clip = ImageClip(str(img_path)).set_duration(scene_duration)
            img_clip = img_clip.resize(width=LONG_WIDTH)
            if img_clip.h > LONG_HEIGHT:
                img_clip = img_clip.crop(x1=0, y1=(img_clip.h - LONG_HEIGHT) / 2, x2=LONG_WIDTH, y2=(img_clip.h + LONG_HEIGHT) / 2)
            
            video_clips.append(img_clip)
            all_allocated_clips.append(img_clip)

        final_audio = concatenate_audioclips(audio_clips)
        final_visual = concatenate_videoclips(video_clips, method="compose")
        total_duration = final_audio.duration
        all_allocated_clips.extend([final_audio, final_visual])

        banner_h = 80
        banner_file = create_breaking_news_banner(LONG_WIDTH, banner_h, video_title, is_breaking=False)
        banner_clip = ImageClip(banner_file).set_duration(total_duration).set_pos((0, LONG_HEIGHT - banner_h - 40))
        all_allocated_clips.append(banner_clip)

        final_video = CompositeVideoClip([final_visual, banner_clip], size=(LONG_WIDTH, LONG_HEIGHT)).set_audio(final_audio)
        all_allocated_clips.append(final_video)

        final_video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="8000k",
            preset="ultrafast",
            threads=4,
            logger=None
        )

        logging.info(f"✓ Long Video ready: {output_path.name}")
        return output_path

    finally:
        for c in all_allocated_clips:
            try:
                c.close()
            except Exception:
                pass
