import logging
from pathlib import Path
from moviepy.editor import ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips, clips_array, ColorClip
from config import WIDTH, HEIGHT, FPS

def create_split_screen_video(scene_data_list, audio_path, output_path, background_video_path=None):
    try:
        audio = AudioFileClip(str(audio_path))
        total_duration = audio.duration
        top_height = HEIGHT // 2

        duration_per_image = total_duration / len(scene_data_list)

        top_clips = []
        for item in scene_data_list:
            img_path = item["image_path"]
            clip = ImageClip(str(img_path)).set_duration(duration_per_image)
            clip = clip.resize(width=WIDTH)
            if clip.h > top_height:
                clip = clip.crop(x1=0, y1=(clip.h - top_height)/2, x2=WIDTH, y2=(clip.h + top_height)/2)
            top_clips.append(clip)

        top_final = concatenate_videoclips(top_clips, method="compose")

        if background_video_path and Path(background_video_path).exists():
            bottom_clip = VideoFileClip(str(background_video_path))
            if bottom_clip.duration < total_duration:
                bottom_clip = bottom_clip.loop(duration=total_duration)
            else:
                bottom_clip = bottom_clip.subclip(0, total_duration)
            bottom_clip = bottom_clip.resize(width=WIDTH)
            if bottom_clip.h > top_height:
                bottom_clip = bottom_clip.crop(x1=0, y1=(bottom_clip.h - top_height)/2, x2=WIDTH, y2=(bottom_clip.h + top_height)/2)
        else:
            bottom_clip = ColorClip(size=(WIDTH, top_height), color=(15, 20, 30)).set_duration(total_duration)

        final_split = clips_array([[top_final], [bottom_clip]])
        final_clip = final_split.set_audio(audio)

        final_clip.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="8000k",
            logger=None
        )

        audio.close()
        final_clip.close()
        return output_path

    except Exception as e:
        logging.exception("Split-screen video editing failed:")
        raise RuntimeError(f"Video assembly failed: {e}")
