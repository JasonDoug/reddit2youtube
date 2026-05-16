import os
import hashlib
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")


def fetch_stock_image(query: str, index: int = 0) -> str | None:
    """Fetch a stock image from Unsplash (free tier). Falls back to Pexels if no key."""
    try:
        if UNSPLASH_ACCESS_KEY:
            url = "https://api.unsplash.com/photos/random"
            params = {"query": query, "orientation": "landscape", "count": 1}
            headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.ok:
                data = r.json()
                img_url = data[0]["urls"]["regular"] if isinstance(data, list) else data["urls"]["regular"]
                return _download_image(img_url, query, index)

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
                    return _download_image(img_url, query, index)

        return _create_placeholder_image(query, index)
    except Exception as e:
        return _create_placeholder_image(query, index)


def _download_image(url: str, query: str, index: int) -> str:
    h = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8]
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
    """Create a stylized placeholder image with text when no stock API is available."""
    colors = [
        (30, 30, 60), (60, 20, 20), (20, 50, 30),
        (50, 30, 60), (60, 50, 20), (20, 40, 60),
    ]
    bg_color = colors[index % len(colors)]
    img = Image.new("RGB", (1920, 1080), bg_color)
    draw = ImageDraw.Draw(img)

    for i in range(0, 1920, 80):
        draw.line([(i, 0), (i + 200, 1080)], fill=(bg_color[0] + 15, bg_color[1] + 15, bg_color[2] + 15), width=1)

    text = query[:60]
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (1920 - text_w) // 2
    y = (1080 - text_h) // 2

    draw.rectangle([x - 20, y - 20, x + text_w + 20, y + text_h + 20], fill=(0, 0, 0, 128))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    h = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8]
    filename = f"placeholder_{h}.jpg"
    path = OUTPUT_DIR / filename
    img.save(str(path), "JPEG", quality=90)
    return str(path)


def prepare_images_for_video(
    image_prompts: list[str],
    use_stock: bool = True,
    aspect_ratio: str = "16:9",
) -> list[str]:
    """
    Given a list of image prompts, fetch/generate images and return file paths.
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
        "1:1": (1080, 1080),
        "4:3": (1440, 1080),
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
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    p = Path(path)
    out_path = p.parent / f"{p.stem}_{aspect_ratio.replace(':', 'x')}.jpg"
    img.save(str(out_path), "JPEG", quality=90)
    return str(out_path)
