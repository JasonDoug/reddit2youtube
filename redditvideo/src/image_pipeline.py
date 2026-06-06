import os
import hashlib
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

_STOPWORDS = {
    "a","an","the","and","or","of","in","on","at","with","for",
    "to","by","from","as","is","was","are","were","be","been",
    "being","that","this","it","its","their","they","we","you","i",
    "he","she","but","not","no","so","about","after","before","when",
}


def _extract_keywords(prompt: str, max_words: int = 3) -> str:
    words = [
        w.lower().strip(".,!?;:'\"")
        for w in prompt.split()
        if w.lower().strip(".,!?;:'\"") not in _STOPWORDS
        and len(w.strip(".,!?;:'\"")) > 2
    ]
    return ",".join(words[:max_words]) if words else "nature"


def fetch_stock_image(query: str, index: int = 0) -> str | None:
    """
    Fetch a topic-matched image. Priority order:
      1. Unsplash  (if UNSPLASH_ACCESS_KEY is set)
      2. Pexels    (if PEXELS_API_KEY is set)
      3. Loremflickr — free, keyword-matched real photos, no API key needed
      4. Stylised gradient placeholder (offline fallback)
    """
    try:
        # ── 1. Unsplash ───────────────────────────────────────────────────────
        if UNSPLASH_ACCESS_KEY:
            url = "https://api.unsplash.com/photos/random"
            params = {"query": query, "orientation": "landscape", "count": 1}
            headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.ok:
                data = r.json()
                img_url = (
                    data[0]["urls"]["regular"]
                    if isinstance(data, list)
                    else data["urls"]["regular"]
                )
                return _download_image(img_url, f"unsplash_{query}", index)

        # ── 2. Pexels ─────────────────────────────────────────────────────────
        pexels_key = os.environ.get("PEXELS_API_KEY", "")
        if pexels_key:
            url = "https://api.pexels.com/v1/search"
            params = {"query": query, "per_page": 5, "orientation": "landscape"}
            headers = {"Authorization": pexels_key}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.ok:
                photos = r.json().get("photos", [])
                if photos:
                    img_url = photos[index % len(photos)]["src"]["large"]
                    return _download_image(img_url, f"pexels_{query}", index)

        # ── 3. Loremflickr (free, keyword-matched) ────────────────────────────
        return _fetch_loremflickr(query, index)

    except Exception:
        return _fetch_loremflickr(query, index)


def _fetch_loremflickr(query: str, index: int) -> str:
    """
    Download a keyword-matched photo from loremflickr.com.
    Uses the prompt keywords so images are topic-relevant.
    The `lock` integer makes results deterministic per prompt+index.
    Falls back to a gradient placeholder if the network is unavailable.
    """
    keywords = _extract_keywords(query, max_words=2)
    seed_int = int(hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8], 16) % 10000
    cache_path = OUTPUT_DIR / f"lf_{hashlib.md5(f'{query}{index}'.encode()).hexdigest()[:10]}.jpg"

    if cache_path.exists():
        return str(cache_path)

    try:
        url = f"https://loremflickr.com/1920/1080/{keywords}?lock={seed_int}"
        r = requests.get(url, timeout=20, allow_redirects=True)
        r.raise_for_status()
        with open(cache_path, "wb") as f:
            f.write(r.content)
        img = Image.open(cache_path).convert("RGB")
        img = img.resize((1920, 1080), Image.LANCZOS)
        img.save(str(cache_path), "JPEG", quality=92)
        return str(cache_path)
    except Exception:
        return _create_placeholder_image(query, index)


def _download_image(url: str, cache_key: str, index: int) -> str:
    h = hashlib.md5(f"{cache_key}{index}".encode()).hexdigest()[:8]
    filename = f"img_{h}.jpg"
    path = OUTPUT_DIR / filename
    if path.exists():
        return str(path)
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    img = Image.open(path).convert("RGB")
    img = img.resize((1920, 1080), Image.LANCZOS)
    img.save(str(path), "JPEG", quality=90)
    return str(path)


def _create_placeholder_image(query: str, index: int) -> str:
    """Vibrant gradient placeholder — used only when the network is offline."""
    PALETTES = [
        ((25,  90, 170), (100, 200, 255)),
        ((170, 30, 100), (255, 130, 180)),
        ((20,  130,  80), (140, 230, 160)),
        ((160,  80,  20), (255, 200,  80)),
        ((100,  20, 160), (200, 120, 255)),
        ((20,  110, 140), ( 80, 220, 220)),
    ]
    dark, light = PALETTES[index % len(PALETTES)]
    img = Image.new("RGB", (1920, 1080))
    draw = ImageDraw.Draw(img)
    for x in range(1920):
        t = x / 1919
        r = int(dark[0] + (light[0] - dark[0]) * t)
        g = int(dark[1] + (light[1] - dark[1]) * t)
        b = int(dark[2] + (light[2] - dark[2]) * t)
        draw.line([(x, 0), (x, 1080)], fill=(r, g, b))

    overlay = Image.new("RGB", (1920, 220), (0, 0, 0))
    img.paste(overlay, (0, 430))
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_sm = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except Exception:
        font_lg = ImageFont.load_default()
        font_sm = font_lg

    text = query[:70]
    bbox = draw.textbbox((0, 0), text, font=font_lg)
    draw.text(((1920 - (bbox[2] - bbox[0])) // 2, 460), text,
              fill=(255, 255, 255), font=font_lg)

    h = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8]
    path = OUTPUT_DIR / f"placeholder_{h}.jpg"
    img.save(str(path), "JPEG", quality=90)
    return str(path)


def prepare_images_for_video(
    image_prompts: list[str],
    use_stock: bool = True,
    aspect_ratio: str = "16:9",
) -> list[str]:
    image_paths = []
    for i, prompt in enumerate(image_prompts):
        path = fetch_stock_image(prompt, i) if use_stock else _create_placeholder_image(prompt, i)
        if path:
            image_paths.append(_resize_for_aspect(path, aspect_ratio))
    return image_paths


def _resize_for_aspect(path: str, aspect_ratio: str) -> str:
    ratios = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1":  (1080, 1080),
        "4:3":  (1440, 1080),
    }
    target_w, target_h = ratios.get(aspect_ratio, (1920, 1080))
    img = Image.open(path).convert("RGB")
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        new_h = target_h
        new_w = int(src_w * (target_h / src_h))
    else:
        new_w = target_w
        new_h = int(src_h * (target_w / src_w))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    img  = img.crop((left, top, left + target_w, top + target_h))
    p = Path(path)
    out_path = p.parent / f"{p.stem}_{aspect_ratio.replace(':', 'x')}.jpg"
    img.save(str(out_path), "JPEG", quality=90)
    return str(out_path)
