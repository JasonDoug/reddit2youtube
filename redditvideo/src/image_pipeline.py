import os
import hashlib
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")


def fetch_stock_image(query: str, index: int = 0) -> str | None:
    """
    Fetch an image for a given query. Priority order:
      1. Unsplash (if UNSPLASH_ACCESS_KEY is set)
      2. Pexels   (if PEXELS_API_KEY is set)
      3. Picsum Photos — free real photos, no API key needed
      4. Stylised placeholder (last resort / offline fallback)
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

        # ── 3. Picsum Photos (free, no key, real photos) ──────────────────────
        return _fetch_picsum(query, index)

    except Exception:
        return _fetch_picsum(query, index)


def _fetch_picsum(query: str, index: int) -> str:
    """
    Download a real photo from Picsum Photos (https://picsum.photos).
    Uses a deterministic seed derived from the query + index so the same
    prompt always fetches the same image (good for caching).
    Falls back to a stylised placeholder if the network is unavailable.
    """
    seed = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:12]
    cache_path = OUTPUT_DIR / f"picsum_{seed}.jpg"

    if cache_path.exists():
        return str(cache_path)

    try:
        # 1920×1080 landscape photo keyed by seed — completely free
        r = requests.get(
            f"https://picsum.photos/seed/{seed}/1920/1080",
            timeout=15,
            allow_redirects=True,
        )
        r.raise_for_status()
        with open(cache_path, "wb") as f:
            f.write(r.content)
        # Verify it's a valid image
        img = Image.open(cache_path).convert("RGB")
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
    """
    Vibrant gradient placeholder — used only when the network is fully
    unavailable. Much brighter than the old near-black cards so it is
    obvious these are actual frames, not a black screen.
    """
    PALETTES = [
        ((25, 90, 170),  (100, 200, 255)),   # blue → cyan
        ((170, 30, 100), (255, 130, 180)),    # magenta → pink
        ((20, 130, 80),  (140, 230, 160)),    # green → mint
        ((160, 80, 20),  (255, 200, 80)),     # orange → gold
        ((100, 20, 160), (200, 120, 255)),    # purple → violet
        ((20, 110, 140), (80, 220, 220)),     # teal → aqua
    ]
    dark, light = PALETTES[index % len(PALETTES)]

    img = Image.new("RGB", (1920, 1080))
    draw = ImageDraw.Draw(img)

    # Simple left-to-right gradient
    for x in range(1920):
        t = x / 1919
        r = int(dark[0] + (light[0] - dark[0]) * t)
        g = int(dark[1] + (light[1] - dark[1]) * t)
        b = int(dark[2] + (light[2] - dark[2]) * t)
        draw.line([(x, 0), (x, 1080)], fill=(r, g, b))

    # Semi-transparent dark band for text readability
    overlay = Image.new("RGB", (1920, 220), (0, 0, 0))
    img.paste(overlay, (0, 430))
    draw = ImageDraw.Draw(img)

    text = query[:70]
    try:
        font_lg = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64
        )
        font_sm = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
        )
    except Exception:
        font_lg = ImageFont.load_default()
        font_sm = font_lg

    # Centre the main text
    bbox = draw.textbbox((0, 0), text, font=font_lg)
    tw = bbox[2] - bbox[0]
    draw.text(((1920 - tw) // 2, 460), text, fill=(255, 255, 255), font=font_lg)

    label = "Slide image (add UNSPLASH_ACCESS_KEY or PEXELS_API_KEY for topic-matched photos)"
    bbox2 = draw.textbbox((0, 0), label, font=font_sm)
    lw = bbox2[2] - bbox2[0]
    draw.text(((1920 - lw) // 2, 560), label, fill=(200, 200, 200), font=font_sm)

    h = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8]
    path = OUTPUT_DIR / f"placeholder_{h}.jpg"
    img.save(str(path), "JPEG", quality=90)
    return str(path)


def prepare_images_for_video(
    image_prompts: list[str],
    use_stock: bool = True,
    aspect_ratio: str = "16:9",
) -> list[str]:
    """
    Given a list of image prompts, fetch / generate images and return file paths.
    """
    image_paths = []
    for i, prompt in enumerate(image_prompts):
        if use_stock:
            path = fetch_stock_image(prompt, i)
        else:
            path = _create_placeholder_image(prompt, i)

        if path:
            resized = _resize_for_aspect(path, aspect_ratio)
            image_paths.append(resized)

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
