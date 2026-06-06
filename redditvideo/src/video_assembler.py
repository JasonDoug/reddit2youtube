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

_FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"
_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_SERIF_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

# Map each genre to a caption font + accent colour so the on-screen text
# reflects the mood of the video (funny → playful, shocking → bold, etc.).
_GENRE_STYLES = {
    "entertaining / funny":          ("Bangers-Regular.ttf",    "yellow"),
    "shocking / controversial":      ("Anton-Regular.ttf",      "red"),
    "heartwarming / inspirational":  ("Pacifico-Regular.ttf",   "white"),
    "news / current events":         ("BebasNeue-Regular.ttf",  "white"),
    "opinion / commentary":          ("Anton-Regular.ttf",      "white"),
    "story time / narrative":        (None,                     "white"),  # serif
    "mystery / suspense":            ("Creepster-Regular.ttf",  "#7CFF7C"),
    "informative / educational":     ("BebasNeue-Regular.ttf",  "white"),
}


def _resolve_genre_style(genre: str) -> tuple[str, str]:
    """Return (font_file_path, fontcolor) for a genre, with safe fallbacks."""
    font_file, color = _GENRE_STYLES.get((genre or "").strip().lower(),
                                         (None, "white"))
    if font_file is None:
        font_path = _SERIF_PATH if os.path.exists(_SERIF_PATH) else _FONT_PATH
    else:
        candidate = _FONTS_DIR / font_file
        font_path = str(candidate) if candidate.exists() else _FONT_PATH
    return font_path, color


def assemble_video(
    image_paths: list[str],
    audio_path: str,
    output_filename: str,
    aspect_ratio: str = "16:9",
    ken_burns: bool = True,
    transition_duration: float = 0.5,
    fps: int = 30,
    script_text: str = "",
    genre: str = "",
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

    # Frame-align the slide duration so the image change, the zoompan length,
    # and the subtitle window all land on exactly the same frame boundary.
    slide_frames = max(int(round(fps * per_image_duration)), 1)
    slide_dur = slide_frames / fps

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
            input_args.extend(["-loop", "1", "-t", f"{slide_dur:.4f}",
                                "-i", prepared])

        if ken_burns:
            # Upscale before zoompan for smooth sub-pixel panning, then trim
            # each slide to exactly slide_frames so zoompan's per-input-frame
            # expansion can't bleed past the slide and swallow later images.
            big_w, big_h = target_w * 2, target_h * 2
            s = f"{target_w}x{target_h}"
            for i in range(len(image_paths)):
                zoom_dir = i % 4
                if zoom_dir == 0:
                    zexpr = "z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                elif zoom_dir == 1:
                    zexpr = "z='if(lte(zoom,1.0),1.5,max(1.0015,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                elif zoom_dir == 2:
                    zexpr = "z='min(zoom+0.0015,1.3)':x='0':y='0'"
                else:
                    zexpr = "z='min(zoom+0.0015,1.3)':x='iw-iw/zoom':y='ih-ih/zoom'"
                filter_parts.append(
                    f"[{i}:v]scale={big_w}:{big_h},"
                    f"zoompan={zexpr}:d={slide_frames}:s={s}:fps={fps},"
                    f"trim=duration={slide_dur:.4f},setpts=PTS-STARTPTS,"
                    f"setsar=1[v{i}]"
                )
        else:
            for i in range(len(image_paths)):
                filter_parts.append(
                    f"[{i}:v]scale={target_w}:{target_h},setsar=1,fps={fps},"
                    f"trim=duration={slide_dur:.4f},setpts=PTS-STARTPTS[v{i}]")

        concat_inputs = "".join(f"[v{i}]" for i in range(len(image_paths)))
        filter_parts.append(
            f"{concat_inputs}concat=n={len(image_paths)}:v=1:a=0[vout]")

        # ── Burned-in subtitles ───────────────────────────────────────────────
        # Word-by-word "karaoke" captions: each word appears exactly when it is
        # spoken (timed across the whole video) with a quick pop-in zoom.  Font
        # and accent colour are chosen to match the genre.
        # The output is cut by -shortest to the SHORTER of the audio and the
        # slideshow, so time captions over that effective length — otherwise
        # the final words could be scheduled past the end and never show.
        total_duration = len(image_paths) * slide_dur
        effective_duration = min(audio_duration, total_duration)
        font_path, font_color = _resolve_genre_style(genre)
        subtitle_chain, sub_files = _build_subtitle_filters(
            script_text, effective_duration, tmp_dir, target_h, font_path, font_color
        )
        if subtitle_chain:
            filter_parts.append(f"[vout]{subtitle_chain}[vfinal]")
            map_v = "[vfinal]"
        else:
            map_v = "[vout]"

        filter_complex = ";".join(filter_parts)

        # The word-level graph can contain hundreds of drawtext filters, which
        # can exceed command-line length limits — pass it via a script file.
        filter_script = os.path.join(tmp_dir, "filter_complex.txt")
        with open(filter_script, "w", encoding="utf-8") as f:
            f.write(filter_complex)

        # ── FFmpeg command ────────────────────────────────────────────────────
        cmd = (
            ["ffmpeg", "-y"]
            + input_args
            + ["-i", audio_path]
            + ["-filter_complex_script", filter_script]
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

def _split_into_words(text: str) -> list[str]:
    """Split script text into individual words (punctuation kept attached)."""
    text = re.sub(r'\s+', ' ', text).strip()
    return [w for w in text.split(" ") if w]


def _escape_drawtext(text: str) -> str:
    """
    Escape word text for drawtext *textfile* mode.  In textfile mode the
    content is read literally except for backslash escapes and `%{...}`
    expansion, so we only neutralise those (colons/quotes are literal here).
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("%",  "\\%")      # avoid accidental %{...} expansion
    text = text.replace("'",  "\u2019")   # nicer curly apostrophe on screen
    return text


def _build_subtitle_filters(
    script_text: str,
    total_duration: float,
    tmp_dir: str,
    frame_height: int,
    font_path: str = _FONT_PATH,
    font_color: str = "white",
) -> tuple[str, list[str]]:
    """
    Build a chain of FFmpeg drawtext filters that burn word-by-word "karaoke"
    captions onto the video.  Each word appears exactly when it is spoken
    (timing estimated from word length across the whole video) and pops in
    with a quick zoom for that big, punchy short-form look.

    Returns (filter_chain_str, [tmp_files]); ("", []) when there is no script.
    """
    if not script_text or total_duration <= 0:
        return "", []

    words = _split_into_words(script_text)
    if not words:
        return "", []

    # ── Estimate each word's spoken time ──────────────────────────────────────
    # gTTS gives no word timestamps, so weight each word by its length (longer
    # words take longer to say) and spread the weights across the whole video.
    weights = [len(re.sub(r'[^\w]', '', w)) + 2 for w in words]
    total_weight = sum(weights) or 1
    starts: list[float] = []
    acc = 0.0
    for wgt in weights:
        starts.append(acc / total_weight * total_duration)
        acc += wgt
    starts.append(total_duration)  # sentinel end

    # Big, punchy caption sizing — much larger than the old per-slide style.
    base_size = max(64, frame_height // 11)
    pop_size  = int(base_size * 1.32)
    pop_dur   = 0.10                      # how long the zoom-in lasts
    y_center  = f"(h-text_h)/2+{int(frame_height * 0.16)}"   # slightly low-center

    font_arg = f":fontfile='{font_path}'" if os.path.exists(font_path) else ""

    # Each word normally emits two drawtext filters (pop + settle).  For very
    # long scripts that doubles into thousands of filters and slows the encode,
    # so drop the pop phase past this threshold to keep one filter per word.
    use_pop = len(words) <= 280

    filters: list[str] = []
    tmp_files: list[str] = []

    for i, word in enumerate(words):
        escaped = _escape_drawtext(word)
        txt_file = os.path.join(tmp_dir, f"w_{i:04d}.txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(escaped)
        tmp_files.append(txt_file)

        w_start = starts[i]
        w_end   = starts[i + 1]
        pop_end = min(w_start + pop_dur, w_end)

        common = (
            f"{font_arg}"
            f":fontcolor={font_color}"
            f":borderw=12:bordercolor=black"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.6"
            f":x=(w-text_w)/2"
        )

        # Pop-in (larger) for the first instant, then settle to the base size.
        if use_pop and pop_end > w_start:
            filters.append(
                f"drawtext=textfile='{txt_file}'{common}"
                f":fontsize={pop_size}:y={y_center}"
                f":enable='between(t,{w_start:.3f},{pop_end:.3f})'"
            )
            settle_start = pop_end
        else:
            settle_start = w_start
        filters.append(
            f"drawtext=textfile='{txt_file}'{common}"
            f":fontsize={base_size}:y={y_center}"
            f":enable='between(t,{settle_start:.3f},{w_end:.3f})'"
        )

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
