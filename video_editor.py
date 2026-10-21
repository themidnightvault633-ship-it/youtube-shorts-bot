import logging
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from config import FPS

def create_video(image_paths, audio_path, output_path):
    try:
        audio = AudioFileClip(str(audio_path))
        duration_per_image = audio.duration / len(image_paths)

        clips = []
        for img_path in image_paths:
            clip = ImageClip(str(img_path)).set_duration(duration_per_image)
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip = final_clip.set_audio(audio)

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
        logging.exception("Video editing failed:")
        raise RuntimeError(f"Video assembly failed: {e}")
