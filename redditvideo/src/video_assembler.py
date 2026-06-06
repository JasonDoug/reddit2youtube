import os
import re
import subprocess
import tempfile
import shutil
import textwrap
from pathlib import Path
from PIL import Image

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def assemble_video(
    image_paths: list[str],
    audio_path: str,
    output_filename: str,
    aspect_ratio: str = "16:9",
    ken_burns: bool = True,
    transition_duration: float = 0.5,
    fps: int = 30,
    script_text: str = "",
) -> dict:
    """
    Assemble a Ken Burns-style slideshow video with audio and burned-in
    subtitles using FFmpeg.  Returns a dict with output path and metadata.
    """
    if not image_paths:
        return {"error": "No images provided"}
    if not os.path.exists(audio_path):
        return {"error": f"Audio file not found: {audio_path}"}

    output_path = OUTPUT_DIR / output_filename
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration <= 0:
        return {"error": "Could not determine audio duration"}

    per_image_duration = max(audio_duration / len(image_paths), 2.0)

    ratios = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1":  (1080, 1080),
        "4:3":  (1440, 1080),
    }
    target_w, target_h = ratios.get(aspect_ratio, (1920, 1080))

    tmp_dir = tempfile.mkdtemp()
    try:
        # ── Build input args and video filter (Ken Burns / plain scale) ───────
        input_args = []
        filter_parts = []

        for i, img_path in enumerate(image_paths):
            prepared = _prepare_image(img_path, target_w, target_h, tmp_dir, i)
            input_args.extend(["-loop", "1", "-t",
                                str(per_image_duration + transition_duration),
                                "-i", prepared])

        if ken_burns:
            for i in range(len(image_paths)):
                zoom_dir = i % 4
                d = int(fps * per_image_duration)
                s = f"{target_w}x{target_h}"
                if zoom_dir == 0:
                    zp = f"zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"
                elif zoom_dir == 1:
                    zp = f"zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.001))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"
                elif zoom_dir == 2:
                    zp = f"zoompan=z='min(zoom+0.001,1.3)':x='0':y='0':d={d}:s={s}:fps={fps}"
                else:
                    zp = f"zoompan=z='min(zoom+0.001,1.3)':x='iw-iw/zoom':y='ih-ih/zoom':d={d}:s={s}:fps={fps}"
                filter_parts.append(f"[{i}:v]{zp},setsar=1[v{i}]")
        else:
            for i in range(len(image_paths)):
                filter_parts.append(
                    f"[{i}:v]scale={target_w}:{target_h},setsar=1[v{i}]")

        concat_inputs = "".join(f"[v{i}]" for i in range(len(image_paths)))
        filter_parts.append(
            f"{concat_inputs}concat=n={len(image_paths)}:v=1:a=0[vout]")

        # ── Burned-in subtitles ───────────────────────────────────────────────
        # Use the frame-rounded duration (int(fps*t)/fps) so subtitle windows
        # are in exact sync with zoompan's d= frame count.
        actual_slide_dur = int(fps * per_image_duration) / fps
        subtitle_chain, sub_files = _build_subtitle_filters(
            script_text, len(image_paths), actual_slide_dur, tmp_dir, target_h
        )
        if subtitle_chain:
            filter_parts.append(f"[vout]{subtitle_chain}[vfinal]")
            map_v = "[vfinal]"
        else:
            map_v = "[vout]"

        filter_complex = ";".join(filter_parts)

        # ── FFmpeg command ────────────────────────────────────────────────────
        cmd = (
            ["ffmpeg", "-y"]
            + input_args
            + ["-i", audio_path]
            + ["-filter_complex", filter_complex]
            + ["-map", map_v]
            + ["-map", f"{len(image_paths)}:a"]
            + ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
            + ["-c:a", "aac", "-b:a", "192k"]
            + ["-shortest"]
            + ["-movflags", "+faststart"]
            + [str(output_path)]
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return {"error": result.stderr[-2000:]}

        file_size = os.path.getsize(str(output_path))
        actual_duration = _get_video_duration(str(output_path))

        return {
            "path": str(output_path),
            "filename": output_filename,
            "duration_sec": actual_duration,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "resolution": f"{target_w}x{target_h}",
            "fps": fps,
            "num_images": len(image_paths),
            "ken_burns": ken_burns,
            "subtitles": bool(subtitle_chain),
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Subtitle helpers ──────────────────────────────────────────────────────────

def _split_into_sentences(text: str) -> list[str]:
    """Split script text into individual sentences."""
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def _wrap_subtitle(sentence: str, max_chars: int = 42) -> str:
    """Wrap a sentence to at most two lines for on-screen readability."""
    lines = textwrap.wrap(sentence, width=max_chars)
    return "\n".join(lines[:2])


def _escape_drawtext(text: str) -> str:
    """Escape characters that FFmpeg drawtext treats as special."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'",  "\u2019")   # replace straight apostrophe with curly
    text = text.replace(":",  "\\:")
    text = text.replace("%",  "\\%")
    return text


def _build_subtitle_filters(
    script_text: str,
    n_images: int,
    per_image_duration: float,
    tmp_dir: str,
    frame_height: int,
) -> tuple[str, list[str]]:
    """
    Build a chain of FFmpeg drawtext filters (one per slide) that burn
    subtitle text onto the video.  Returns (filter_chain_str, [tmp_files]).
    Returns ("", []) when no script text is provided.
    """
    if not script_text or n_images == 0:
        return "", []

    sentences = _split_into_sentences(script_text)
    if not sentences:
        return "", []

    # Distribute sentences across slides
    chunks: list[str] = []
    total = len(sentences)
    for i in range(n_images):
        start = int(i * total / n_images)
        end   = int((i + 1) * total / n_images)
        chunk_sents = sentences[start:end]
        chunks.append(" ".join(chunk_sents) if chunk_sents else "")

    font_size = max(36, frame_height // 22)
    y_pos     = frame_height - font_size * 3 - 30   # near bottom

    filters: list[str] = []
    tmp_files: list[str] = []

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        wrapped = _wrap_subtitle(chunk, max_chars=44)
        escaped = _escape_drawtext(wrapped)

        t_start = i * per_image_duration
        t_end   = (i + 1) * per_image_duration

        # Write text to a temp file to avoid shell-escaping headaches
        txt_file = os.path.join(tmp_dir, f"sub_{i:04d}.txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(escaped)
        tmp_files.append(txt_file)

        # Font path — fall back gracefully if DejaVu isn't present
        font_arg = f":fontfile='{_FONT_PATH}'" if os.path.exists(_FONT_PATH) else ""
        line_count = wrapped.count("\n") + 1
        effective_y = y_pos - (line_count - 1) * (font_size + 4)

        dt = (
            f"drawtext=textfile='{txt_file}'{font_arg}"
            f":fontsize={font_size}"
            f":fontcolor=white"
            f":box=1:boxcolor=black@0.55:boxborderw=14"
            f":x=(w-text_w)/2:y={effective_y}"
            f":line_spacing=6"
            f":enable='between(t,{t_start:.3f},{t_end:.3f})'"
        )
        filters.append(dt)

    return ",".join(filters), tmp_files


# ── FFmpeg probe helpers ──────────────────────────────────────────────────────

def _prepare_image(img_path: str, target_w: int, target_h: int,
                   tmp_dir: str, index: int) -> str:
    out = os.path.join(tmp_dir, f"frame_{index:04d}.jpg")
    img = Image.open(img_path).convert("RGB")
    img = img.resize((target_w, target_h), Image.LANCZOS)
    img.save(out, "JPEG", quality=95)
    return out


def _get_audio_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _get_video_duration(path: str) -> float:
    return _get_audio_duration(path)
