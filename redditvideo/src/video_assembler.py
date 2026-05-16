import os
import subprocess
from pathlib import Path
from PIL import Image
import tempfile
import shutil

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def assemble_video(
    image_paths: list[str],
    audio_path: str,
    output_filename: str,
    aspect_ratio: str = "16:9",
    ken_burns: bool = True,
    transition_duration: float = 0.5,
    fps: int = 30,
) -> dict:
    """
    Assemble a Ken Burns style slideshow video with audio using FFmpeg.
    Returns dict with output path and metadata.
    """
    if not image_paths:
        return {"error": "No images provided"}
    if not os.path.exists(audio_path):
        return {"error": f"Audio file not found: {audio_path}"}

    output_path = OUTPUT_DIR / output_filename

    audio_duration = _get_audio_duration(audio_path)
    if audio_duration <= 0:
        return {"error": "Could not determine audio duration"}

    per_image_duration = audio_duration / len(image_paths)
    per_image_duration = max(per_image_duration, 2.0)

    ratios = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:3": (1440, 1080),
    }
    target_w, target_h = ratios.get(aspect_ratio, (1920, 1080))

    tmp_dir = tempfile.mkdtemp()
    try:
        filter_parts = []
        input_args = []

        for i, img_path in enumerate(image_paths):
            prepared = _prepare_image(img_path, target_w, target_h, tmp_dir, i)
            input_args.extend(["-loop", "1", "-t", str(per_image_duration + transition_duration), "-i", prepared])

        if ken_burns:
            for i in range(len(image_paths)):
                zoom_dir = i % 4
                if zoom_dir == 0:
                    zoompan = f"zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(fps * per_image_duration)}:s={target_w}x{target_h}:fps={fps}"
                elif zoom_dir == 1:
                    zoompan = f"zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.001))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(fps * per_image_duration)}:s={target_w}x{target_h}:fps={fps}"
                elif zoom_dir == 2:
                    zoompan = f"zoompan=z='min(zoom+0.001,1.3)':x='0':y='0':d={int(fps * per_image_duration)}:s={target_w}x{target_h}:fps={fps}"
                else:
                    zoompan = f"zoompan=z='min(zoom+0.001,1.3)':x='iw-iw/zoom':y='ih-ih/zoom':d={int(fps * per_image_duration)}:s={target_w}x{target_h}:fps={fps}"

                filter_parts.append(f"[{i}:v]{zoompan},setsar=1[v{i}]")
        else:
            for i in range(len(image_paths)):
                filter_parts.append(f"[{i}:v]scale={target_w}:{target_h},setsar=1[v{i}]")

        concat_inputs = "".join(f"[v{i}]" for i in range(len(image_paths)))
        filter_parts.append(f"{concat_inputs}concat=n={len(image_paths)}:v=1:a=0[vout]")
        filter_complex = ";".join(filter_parts)

        cmd = (
            ["ffmpeg", "-y"]
            + input_args
            + ["-i", audio_path]
            + ["-filter_complex", filter_complex]
            + ["-map", "[vout]"]
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
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _prepare_image(img_path: str, target_w: int, target_h: int, tmp_dir: str, index: int) -> str:
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
