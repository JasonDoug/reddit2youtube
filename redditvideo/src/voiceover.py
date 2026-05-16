import os
import hashlib
from pathlib import Path
from gtts import gTTS
from pydub import AudioSegment


OUTPUT_DIR = Path(__file__).parent.parent / "output" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GTTS_LANGUAGES = {
    "English (US)": "en",
    "English (UK)": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Japanese": "ja",
    "Korean": "ko",
    "Hindi": "hi",
}

GTTS_SPEEDS = {
    "Normal": False,
    "Slow": True,
}


def generate_voiceover(
    script: str,
    language: str = "English (US)",
    speed: str = "Normal",
    output_filename: str = "",
) -> dict:
    """
    Generate a voiceover MP3 from script text using gTTS (free Google TTS).
    Returns path to the generated audio file and duration info.
    """
    if not script.strip():
        return {"error": "Script is empty"}

    lang_code = GTTS_LANGUAGES.get(language, "en")
    slow = GTTS_SPEEDS.get(speed, False)

    if not output_filename:
        h = hashlib.md5(script[:100].encode()).hexdigest()[:8]
        output_filename = f"voiceover_{h}.mp3"

    output_path = OUTPUT_DIR / output_filename

    try:
        tts = gTTS(text=script, lang=lang_code, slow=slow)
        tts.save(str(output_path))

        audio = AudioSegment.from_mp3(str(output_path))
        duration_sec = len(audio) / 1000.0

        return {
            "path": str(output_path),
            "filename": output_filename,
            "duration_sec": duration_sec,
            "language": language,
            "speed": speed,
            "word_count": len(script.split()),
        }
    except Exception as e:
        return {"error": str(e)}


def get_audio_duration(path: str) -> float:
    try:
        audio = AudioSegment.from_file(path)
        return len(audio) / 1000.0
    except Exception:
        return 0.0
