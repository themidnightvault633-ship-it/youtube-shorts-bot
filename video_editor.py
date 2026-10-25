import os
import re
import math
import time
import logging
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from image_engine import draw_bilingual_text, _load_font_pair

logger = logging.getLogger("NewsBot.VideoEditor")


def _get_audio_duration(audio_path):
    """Gets exact duration of an audio file in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        return max(2.0, float(out))
    except Exception:
        return 6.5


def _extract_audio_envelope(audio_path, duration, fps=30):
    """
    Extracts a frame-accurate speech amplitude envelope (values 0.0 to 1.0)
    from the voiceover file using FFmpeg raw PCM output.
    """
    n_frames = max(1, int(math.ceil(duration * fps)) + 2)
    sample_rate = 1500
    try:
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-ac", "1", "-ar", str(sample_rate),
            "-f", "s16le", "-",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
        if pcm.size < 10:
            raise ValueError("Empty PCM buffer")

        samples_per_frame = max(1, sample_rate // fps)
        target_len = n_frames * samples_per_frame
        if pcm.size < target_len:
            pcm = np.pad(pcm, (0, target_len - pcm.size))
        else:
            pcm = pcm[:target_len]

        frames_pcm = pcm.reshape((n_frames, samples_per_frame))
        rms = np.sqrt(np.mean(frames_pcm ** 2, axis=1))
        p95 = np.percentile(rms, 95) if rms.size > 0 else 1.0
        env = np.clip(rms / max(p95, 100.0), 0.0, 1.0)
        kernel = np.array([0.2, 0.6, 0.2], dtype=np.float32)
        env = np.convolve(env, kernel, mode="same")
        return env
    except Exception as e:
        logger.debug(f"Audio envelope fallback: {e}")
        t = np.linspace(0, duration, n_frames)
        return 0.45 + 0.45 * np.abs(np.sin(2.0 * np.pi * 3.8 * t))


def _detect_anchor_landmarks(anchor_rgb):
    """
    Detects face center, eye level, and mouth/jaw center in the anchor studio image.
    Uses warm skin-tone centroid within the central portrait zone so mouth & head
    articulation lands naturally on the anchor's face.
    """
    h, w, _ = anchor_rgb.shape
    y0, y1 = int(h * 0.14), int(h * 0.62)
    x0, x1 = int(w * 0.28), int(w * 0.72)
    roi = anchor_rgb[y0:y1, x0:x1].astype(np.float32)
    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]

    skin_mask = (r > 95) & (g > 55) & (b > 35) & ((r - g) > 12) & ((r - b) > 22) & (r < 250)
    if np.count_nonzero(skin_mask) > 400:
        ys, xs = np.where(skin_mask)
        cx = x0 + int(np.median(xs))
        cy_face = y0 + int(np.percentile(ys, 48))
        face_h = max(140, int(np.percentile(ys, 90) - np.percentile(ys, 10)))
        eye_y = cy_face - int(face_h * 0.14)
        mouth_y = cy_face + int(face_h * 0.22)
        return cx, eye_y, mouth_y, face_h

    cx = w // 2
    eye_y = int(h * 0.34)
    mouth_y = int(h * 0.44)
    face_h = int(h * 0.26)
    return cx, eye_y, mouth_y, face_h


class BroadcastAnchorAnimator:
    """
    Fast vectorized 30fps Audio-Reactive TV News Anchor Motion Rig.
    Animates:
      1. Real-time Audio-Synced Mouth & Lower Jaw Articulation
      2. Expressive Head Nods & Breathing Upper-Body Motion
      3. Natural Periodic Eye Blinks
      4. Live Picture-in-Picture (PIP) Studio Wall Monitor behind the anchor
      5. Multi-Camera Cuts (Wide Studio Shot vs Medium Close-Up Shot)
    """

    def __init__(self, anchor_img_path, width=1080, height=790):
        self.w = width
        self.h = height
        raw = Image.open(anchor_img_path).convert("RGB")
        src_w, src_h = raw.size
        target_ratio = width / float(height)
        src_ratio = src_w / float(src_h)
        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            raw = raw.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            raw = raw.crop((0, top, src_w, top + new_h))

        raw = raw.resize((width, height), Image.Resampling.LANCZOS)
        self.base = np.asarray(raw, dtype=np.uint8)

        self.gw = width // 2
        self.gh = height // 2
        self.small_base = np.asarray(
            raw.resize((self.gw, self.gh), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )

        cx, eye_y, mouth_y, face_h = _detect_anchor_landmarks(self.base)
        self.cx = cx // 2
        self.eye_y = eye_y // 2
        self.mouth_y = mouth_y // 2
        self.face_r = max(36, face_h // 4)

        yy, xx = np.meshgrid(
            np.arange(self.gh, dtype=np.float32),
            np.arange(self.gw, dtype=np.float32),
            indexing="ij",
        )
        self.xx = xx
        self.yy = yy

        self.head_mask = np.exp(
            -(((xx - self.cx) / (self.face_r * 1.45)) ** 2 + ((yy - (self.mouth_y - 12)) / (self.face_r * 1.65)) ** 2)
        )
        self.body_mask = np.exp(
            -(((xx - self.cx) / (self.face_r * 2.6)) ** 2 + ((yy - (self.mouth_y + 75)) / (self.face_r * 2.2)) ** 2)
        )
        jaw_cy = self.mouth_y + int(self.face_r * 0.24)
        self.jaw_mask = np.exp(
            -(((xx - self.cx) / (self.face_r * 0.52)) ** 2 + ((yy - jaw_cy) / (self.face_r * 0.38)) ** 2)
        )
        self.lip_aperture = np.exp(
            -(((xx - self.cx) / (self.face_r * 0.26)) ** 2 + ((yy - self.mouth_y) / (self.face_r * 0.11)) ** 2)
        )[:, :, None]

        eye_sep = int(self.face_r * 0.44)
        left_eye = np.exp(-(((xx - (self.cx - eye_sep)) / 11.0) ** 2 + ((yy - self.eye_y) / 5.5) ** 2))
        right_eye = np.exp(-(((xx - (self.cx + eye_sep)) / 11.0) ** 2 + ((yy - self.eye_y) / 5.5) ** 2))
        self.blink_mask = np.clip(left_eye + right_eye, 0.0, 1.0)

    def render_frame(self, t, speech_amp, camera_angle="wide", broll_thumb=None):
        """Renders an animated 30fps studio anchor frame at timestamp t."""
        nod_y = (1.6 * math.sin(t * 2.7) + 2.2 * speech_amp * math.sin(t * 6.5)) * self.head_mask
        sway_x = (1.5 * math.sin(t * 1.4) + 1.0 * speech_amp * math.cos(t * 4.2)) * (self.head_mask + 0.5 * self.body_mask)
        breath_y = 1.2 * math.sin(t * 1.8) * self.body_mask

        jaw_open = (4.8 * (speech_amp ** 1.15) + 0.6 * abs(math.sin(t * 9.0)) * speech_amp) * self.jaw_mask

        blink_phase = (t % 3.4)
        blink_strength = math.exp(-((blink_phase - 1.7) / 0.065) ** 2)
        blink_pull = 3.2 * blink_strength * self.blink_mask

        src_x = np.clip(np.rint(self.xx - sway_x).astype(np.int32), 0, self.gw - 1)
        src_y = np.clip(np.rint(self.yy - nod_y - breath_y - jaw_open - blink_pull).astype(np.int32), 0, self.gh - 1)

        warped_small = self.small_base[src_y, src_x].astype(np.float32)

        if speech_amp > 0.18:
            shade = 1.0 - (0.38 * speech_amp * self.lip_aperture)
            warped_small = warped_small * shade

        warped_uint8 = np.clip(warped_small, 0, 255).astype(np.uint8)
        frame_pil = Image.fromarray(warped_uint8).resize((self.w, self.h), Image.Resampling.BILINEAR)

        if broll_thumb is not None:
            pip_w, pip_h = min(240, self.w // 4), min(140, self.h // 5)
            pip_img = broll_thumb.resize((pip_w, pip_h), Image.Resampling.BILINEAR)
            draw_pip = ImageDraw.Draw(frame_pil)
            px, py = self.w - pip_w - 24, 34
            draw_pip.rectangle([px - 4, py - 4, px + pip_w + 4, py + pip_h + 4], fill=(225, 30, 45), outline=(255, 200, 0), width=2)
            frame_pil.paste(pip_img, (px, py))

        if camera_angle == "closeup":
            zoom = 1.14 + 0.02 * math.sin(t * 0.5)
        else:
            zoom = 1.02 + 0.03 * math.sin(t * 0.4)

        cw = int(self.w / zoom)
        ch = int(self.h / zoom)
        x0 = (self.w - cw) // 2
        y0 = max(0, int((self.h - ch) * 0.32))
        frame_pil = frame_pil.crop((x0, y0, x0 + cw, y0 + ch)).resize((self.w, self.h), Image.Resampling.BILINEAR)
        return np.asarray(frame_pil, dtype=np.uint8)


def _split_caption_chunks(text, max_words_per_chunk=7):
    """Splits scene narration into readable subtitle chunks synced across the scene duration."""
    words = (text or "").strip().split()
    if not words:
        return [""]
    chunks = []
    for i in range(0, len(words), max_words_per_chunk):
        chunks.append(" ".join(words[i : i + max_words_per_chunk]))
    return chunks


def _create_bgm_wav(total_duration, bgm_path="temp/broadcast_bgm.wav"):
    """Synthesizes a subtle, authoritative TV Newsroom pulse bed via NumPy."""
    sr = 22050
    n_samples = int(total_duration * sr)
    t = np.linspace(0, total_duration, n_samples, endpoint=False)
    pad = 0.35 * np.sin(2 * np.pi * 110.0 * t) + 0.25 * np.sin(2 * np.pi * 165.0 * t)
    pulse = (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)) ** 3
    beeps = 0.20 * np.sin(2 * np.pi * 440.0 * t) * pulse
    wave = np.clip((pad + beeps) * 0.045, -0.9, 0.9)

    os.makedirs(os.path.dirname(os.path.abspath(bgm_path)), exist_ok=True)
    pcm16 = (wave * 32767).astype(np.int16)
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
        bgm_path,
    ]
    subprocess.run(cmd, input=pcm16.tobytes(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    return bgm_path if os.path.exists(bgm_path) else None


def build_news_video(script_data, scene_assets, output_path, is_short=True, anchor_img_path=None):
    """
    Assembles a 30fps BBC News / Aaj Tak / News 24 television broadcast video
    for BOTH Vertical Shorts (1080x1920) AND Horizontal Long Videos (1920x1080).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    fps = 30
    W, H = (1080, 1920) if is_short else (1920, 1080)

    language = script_data.get("language", "hindi")
    category = script_data.get("category", "NATION").upper()
    ticker_raw = script_data.get("ticker_text") or script_data.get("headline_banner") or "LIVE BREAKING NEWS UPDATES"

    ticker_clean = re.sub(r"•", " | ", ticker_raw)
    ticker_unit = f"   [LIVE 24x7]  {ticker_clean}   |   BREAKING NEWS   |   "
    ticker_full = ticker_unit * 4

    ticker_w = max(W * 4, len(ticker_full) * 18)
    ticker_h = 56
    ticker_strip = Image.new("RGB", (ticker_w, ticker_h), (245, 196, 0))
    t_draw = ImageDraw.Draw(ticker_strip)
    t_draw.rectangle([0, 0, ticker_w, 4], fill=(190, 15, 25))
    end_x = draw_bilingual_text(t_draw, (20, 10), ticker_full, size=30, fill=(10, 12, 18))
    unit_px = max(450, (end_x - 20) // 4)
    ticker_arr = np.asarray(ticker_strip, dtype=np.uint8)

    if is_short:
        broll_win_w, broll_win_h = W, 820
        anchor_w, anchor_h = W, 790
        strap_h = 112
        sub_h = 98
        max_words_chunk = 7
        hl_max_chars = 44
    else:
        # 16:9 Horizontal TV Broadcast Split Screen (1920x1080)
        broll_win_w, broll_win_h = 1120, 850
        anchor_w, anchor_h = 800, 850
        strap_h = 86
        sub_h = 88
        max_words_chunk = 12
        hl_max_chars = 78

    animator = BroadcastAnchorAnimator(anchor_img_path, width=anchor_w, height=anchor_h)

    prepared_scenes = []
    concat_list_path = "temp/audio_concat.txt"
    total_duration = 0.0

    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for idx, asset in enumerate(scene_assets):
            dur = _get_audio_duration(asset["audio_path"])
            env = _extract_audio_envelope(asset["audio_path"], dur, fps=fps)
            f_concat.write(f"file '{os.path.abspath(asset['audio_path'])}'\n")

            broll_pil = Image.open(asset["image_path"]).convert("RGB")
            broll_base = broll_pil.resize((int(broll_win_w * 1.14), int(broll_win_h * 1.14)), Image.Resampling.LANCZOS)
            broll_thumb = broll_pil.resize((240, 140), Image.Resampling.BILINEAR)

            headline_banner = asset.get("headline_banner") or script_data.get("headline_banner", "BREAKING NEWS")
            narration = asset.get("subtitles") or asset.get("narration", "")
            cam_angle = asset.get("camera_angle", "closeup" if idx % 2 == 1 else "wide")
            caption_chunks = _split_caption_chunks(narration, max_words_per_chunk=max_words_chunk)

            strap_img = Image.new("RGBA", (W, strap_h), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(strap_img)
            s_draw.rectangle([0, 0, W, strap_h], fill=(155, 12, 24, 248))
            s_draw.rectangle([0, 0, W, 5], fill=(255, 205, 0, 255))
            s_draw.rectangle([0, strap_h - 5, W, strap_h], fill=(255, 205, 0, 255))
            badge_label = "बड़ी ख़बर" if language == "hindi" else "BREAKING"
            s_draw.polygon([(0, 5), (245, 5), (220, strap_h - 5), (0, strap_h - 5)], fill=(250, 195, 0, 255))
            ty_strap = (strap_h - 34) // 2
            draw_bilingual_text(s_draw, (24, ty_strap), badge_label, size=28, fill=(15, 15, 20, 255))

            hl_clean = headline_banner.strip()
            if len(hl_clean) > hl_max_chars:
                hl_clean = hl_clean[: hl_max_chars - 2] + "..."
            draw_bilingual_text(s_draw, (256, ty_strap - 2), hl_clean, size=34, fill=(255, 255, 255, 255))
            strap_rgb = np.asarray(strap_img.convert("RGB"), dtype=np.uint8)

            sub_cards = []
            for chunk in caption_chunks:
                sc_img = Image.new("RGB", (W, sub_h), (10, 14, 28))
                sc_draw = ImageDraw.Draw(sc_img)
                sc_draw.rectangle([0, 0, W, 4], fill=(0, 195, 255))
                sc_draw.rounded_rectangle([24, 10, W - 24, sub_h - 8], radius=12, fill=(18, 24, 46), outline=(255, 205, 0), width=2)
                cy_dot = sub_h // 2
                sc_draw.ellipse([42, cy_dot - 9, 60, cy_dot + 9], fill=(235, 30, 45))
                speaker_tag = "एंकर:" if language == "hindi" else "ANCHOR:"
                draw_bilingual_text(sc_draw, (72, cy_dot - 19), f"{speaker_tag}  {chunk}", size=32, fill=(255, 248, 210))
                sub_cards.append(np.asarray(sc_img, dtype=np.uint8))

            prepared_scenes.append({
                "idx": idx,
                "dur": dur,
                "start_t": total_duration,
                "env": env,
                "broll_base": broll_base,
                "broll_thumb": broll_thumb,
                "strap_rgb": strap_rgb,
                "sub_cards": sub_cards,
                "cam_angle": cam_angle,
            })
            total_duration += dur

    merged_voice_wav = "temp/merged_voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-ar", "24000", "-ac", "1", merged_voice_wav],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=45,
    )
    bgm_wav = _create_bgm_wav(total_duration, "temp/broadcast_bgm.wav")
    final_audio_wav = "temp/final_mixed_audio.wav"
    if bgm_wav and os.path.exists(merged_voice_wav):
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", merged_voice_wav,
                "-i", bgm_wav,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[aout]",
                final_audio_wav,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
    else:
        final_audio_wav = merged_voice_wav

    logger.info(f"🎬 Rendering 30fps {'SHORT (9:16)' if is_short else 'LONG (16:9)'} Video ({total_duration:.1f}s) to {output_path}...")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-i", final_audio_wav,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for sc in prepared_scenes:
        n_frames = max(1, int(round(sc["dur"] * fps)))
        idx = sc["idx"]
        dur = sc["dur"]
        env = sc["env"]
        broll_base = sc["broll_base"]
        broll_thumb = sc["broll_thumb"]
        strap_rgb = sc["strap_rgb"]
        sub_cards = sc["sub_cards"]
        cam_angle = sc["cam_angle"]
        scene_start_t = sc["start_t"]

        for f_i in range(n_frames):
            t = f_i / float(fps)
            gt = scene_start_t + t
            speech_amp = float(env[min(len(env) - 1, f_i)])

            prog = min(1.0, max(0.0, t / max(0.1, dur)))
            bw, bh = broll_base.size
            if idx % 2 == 0:
                crop_x = int((bw - broll_win_w) * prog * 0.75)
                crop_y = int((bh - broll_win_h) * (1.0 - prog) * 0.65)
            else:
                crop_x = int((bw - broll_win_w) * (1.0 - prog) * 0.75)
                crop_y = int((bh - broll_win_h) * prog * 0.65)
            top_pil = broll_base.crop((crop_x, crop_y, crop_x + broll_win_w, crop_y + broll_win_h)).copy()

            top_draw = ImageDraw.Draw(top_pil)
            pulse_red = (235, 20, 35) if int(gt * 2.5) % 2 == 0 else (175, 12, 22)
            top_draw.rounded_rectangle([32, 36, 248, 90], radius=10, fill=pulse_red, outline=(255, 255, 255), width=2)
            top_draw.ellipse([50, 53, 70, 73], fill=(255, 255, 255))
            draw_bilingual_text(top_draw, (82, 46), "LIVE 24x7", size=26, fill=(255, 255, 255))

            top_draw.rounded_rectangle([260, 36, 475, 90], radius=10, fill=(14, 22, 48), outline=(255, 200, 0), width=2)
            draw_bilingual_text(top_draw, (282, 46), category, size=26, fill=(255, 215, 0))
            broll_arr = np.asarray(top_pil, dtype=np.uint8)

            anchor_arr = animator.render_frame(
                gt,
                speech_amp=speech_amp,
                camera_angle=cam_angle,
                broll_thumb=broll_thumb if is_short else None,
            )

            canvas = np.zeros((H, W, 3), dtype=np.uint8)
            chunk_idx = min(len(sub_cards) - 1, int((t / max(0.1, dur)) * len(sub_cards)))
            scroll_x = int(gt * 165) % max(1, min(unit_px, ticker_arr.shape[1] - W - 1))

            if is_short:
                # Vertical 9:16 Layout (1080x1920)
                canvas[0:820, :, :] = broll_arr
                canvas[820:932, :, :] = strap_rgb
                canvas[932:1722, :, :] = anchor_arr
                canvas[1445:1543, :, :] = sub_cards[chunk_idx]

                bar_w = int(W * (0.18 + 0.72 * speech_amp))
                x_start = (W - bar_w) // 2
                canvas[1435:1443, x_start : x_start + bar_w, :] = (255, 65, 75)
                canvas[1543:1599, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]
                canvas[1599:1606, :, :] = (220, 25, 35)
            else:
                # Horizontal 16:9 Prime-Time TV Layout (1920x1080)
                canvas[0:850, 0:1120, :] = broll_arr
                canvas[0:850, 1120:1920, :] = anchor_arr
                canvas[0:850, 1116:1124, :] = (255, 200, 0)
                canvas[850:936, :, :] = strap_rgb
                canvas[936:1024, :, :] = sub_cards[chunk_idx]
                canvas[1024:1080, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]

            proc.stdin.write(canvas.tobytes())

    proc.stdin.close()
    proc.wait(timeout=180)
    logger.info(f"✅ Broadcast Video Rendered: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
    return output_path
