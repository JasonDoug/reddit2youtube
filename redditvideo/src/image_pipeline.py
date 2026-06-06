import os
import io
import base64
import hashlib
import threading
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

# Per-cache-key locks so concurrent slides with the SAME prompt (which map to
# the same cache file) serialize instead of racing on a half-written file.
_KEY_LOCKS: dict[str, threading.Lock] = {}
_KEY_LOCKS_GUARD = threading.Lock()


def _key_lock(key: str) -> threading.Lock:
    with _KEY_LOCKS_GUARD:
        lock = _KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _KEY_LOCKS[key] = lock
        return lock

# Valid image sources, in order of how well they match the script subject.
SOURCE_AI = "ai"            # AI-generated to match each prompt (best match)
SOURCE_STOCK = "stock"      # Unsplash/Pexels search → Picsum random fallback
SOURCE_PLACEHOLDER = "placeholder"


def prepare_images_for_video(
    image_prompts: list[str],
    source: str = SOURCE_AI,
    aspect_ratio: str = "16:9",
    use_stock: bool | None = None,   # legacy kwarg, kept for old callers
) -> list[str]:
    """
    Generate / fetch one image per prompt and return resized file paths.

    source:
      • "ai"          → AI-generated images that match each prompt's subject
      • "stock"       → Unsplash/Pexels (if keyed) else random Picsum photos
      • "placeholder" → offline gradient cards
    """
    # Back-compat: older call sites passed use_stock as the 2nd arg (now
    # `source`), either positionally (a bool) or as a keyword.
    if isinstance(source, bool):
        source = SOURCE_STOCK if source else SOURCE_PLACEHOLDER
    elif use_stock is not None and source == SOURCE_AI:
        source = SOURCE_STOCK if use_stock else SOURCE_PLACEHOLDER

    # Seed derived from the combined prompts so each script gets its own
    # starting offset in the Picsum library (stock fallback only).
    combined = "|".join(image_prompts)
    base_seed = int(hashlib.md5(combined.encode()).hexdigest()[:6], 16) % 500

    def _one(i: int, prompt: str) -> str | None:
        # A single bad slide must never abort the whole batch, so every path
        # is wrapped and degrades to a placeholder as a last resort.
        try:
            if source == SOURCE_AI:
                # AI generation is independent per slide and slow, so callers
                # run these concurrently. Fall back to stock if it fails.
                path = _generate_ai_image(prompt, index=i, aspect_ratio=aspect_ratio)
                if not path:
                    path = _fetch_stock_image(prompt, index=i, base_seed=base_seed)
            elif source == SOURCE_STOCK:
                path = _fetch_stock_image(prompt, index=i, base_seed=base_seed)
            else:
                path = _create_placeholder_image(prompt, i)
            if not path:
                return None
            return _resize_for_aspect(path, aspect_ratio)
        except Exception:
            try:
                return _resize_for_aspect(_create_placeholder_image(prompt, i), aspect_ratio)
            except Exception:
                return None

    # Generate AI images in parallel (each call is ~15-40s); fetch others
    # serially since they are fast and rate-limit-friendly.
    if source == SOURCE_AI and len(image_prompts) > 1:
        from concurrent.futures import ThreadPoolExecutor
        results: list[str | None] = [None] * len(image_prompts)
        with ThreadPoolExecutor(max_workers=min(len(image_prompts), 5)) as ex:
            futures = {ex.submit(_one, i, p): i for i, p in enumerate(image_prompts)}
            for fut in futures:
                results[futures[fut]] = fut.result()
        return [p for p in results if p]

    out: list[str] = []
    for i, prompt in enumerate(image_prompts):
        path = _one(i, prompt)
        if path:
            out.append(path)
    return out


# ── AI image generation ───────────────────────────────────────────────────────

# gpt-image-1 only accepts these three sizes; pick the nearest to the aspect.
_AI_SIZE_FOR_ASPECT = {
    "16:9": "1536x1024",
    "4:3":  "1536x1024",
    "9:16": "1024x1536",
    "1:1":  "1024x1024",
}


def _ai_client():
    """OpenAI SDK client pointed at the Replit AI Integrations proxy (no key)."""
    from openai import OpenAI
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
    if base_url:
        return OpenAI(base_url=base_url, api_key=api_key)
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return None


def _generate_ai_image(prompt: str, index: int, aspect_ratio: str) -> str | None:
    """
    Generate an image that matches `prompt` using gpt-image-1 via the Replit
    OpenAI proxy. Cached by (prompt, aspect) so re-runs don't regenerate.
    Returns the file path, or None if generation is unavailable.
    """
    size = _AI_SIZE_FOR_ASPECT.get(aspect_ratio, "1536x1024")
    key = hashlib.md5(f"{prompt}|{size}".encode()).hexdigest()[:10]
    cache_path = OUTPUT_DIR / f"ai_{key}.jpg"

    # Serialize same-key requests: duplicate prompts in one batch share this
    # cache file, so the first thread generates and the rest hit the cache
    # instead of racing on a half-written file.
    with _key_lock(key):
        if cache_path.exists():
            return str(cache_path)

        client = _ai_client()
        if client is None:
            return None

        # Style the prompt for clean, cinematic, subject-relevant stills.
        styled = (
            f"{prompt}. Cinematic, high detail, dramatic lighting, photorealistic, "
            f"vivid colors, professional photography, no text, no watermark."
        )
        try:
            resp = client.images.generate(
                model="gpt-image-1", prompt=styled, size=size, n=1,
            )
            b64 = getattr(resp.data[0], "b64_json", None)
            if not b64:
                return None
            # Decode, normalize to JPEG, and publish atomically so readers
            # never observe a partially written cache file.
            tmp_path = cache_path.with_suffix(".tmp.jpg")
            Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB").save(
                str(tmp_path), "JPEG", quality=92
            )
            os.replace(str(tmp_path), str(cache_path))
            return str(cache_path)
        except Exception:
            return None


# ── Image fetchers ────────────────────────────────────────────────────────────

def _fetch_stock_image(query: str, index: int, base_seed: int) -> str | None:
    """
    Priority:
      1. Unsplash  (if UNSPLASH_ACCESS_KEY is set)
      2. Pexels    (if PEXELS_API_KEY is set)
      3. Picsum Photos — free, guaranteed unique per slide, no API key needed
      4. Gradient placeholder — offline last resort
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
                return _download_and_cache(img_url, f"unsplash_{query}", index)

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
                    return _download_and_cache(img_url, f"pexels_{query}", index)

        # ── 3. Picsum Photos (free, guaranteed unique per slide) ──────────────
        return _fetch_picsum(base_seed, index)

    except Exception:
        return _fetch_picsum(base_seed, index)


def _fetch_picsum(base_seed: int, index: int) -> str:
    """
    Download a unique photo from Picsum Photos (https://picsum.photos).

    Photo ID formula: (base_seed + index * 97) % 1000
    • 97 is prime and coprime with 1000 → no repeats within a 1000-slide run
    • base_seed varies per script → different scripts get different photo sets
    • Cached by photo ID → same ID never downloaded twice
    """
    photo_id = (base_seed + index * 97) % 1000
    cache_path = OUTPUT_DIR / f"picsum_{photo_id:04d}.jpg"

    if cache_path.exists():
        return str(cache_path)

    try:
        # seed-based URL: always returns a valid photo (no 404s unlike /id/)
        r = requests.get(
            f"https://picsum.photos/seed/{photo_id}/1920/1080",
            timeout=20,
            allow_redirects=True,
        )
        r.raise_for_status()
        with open(cache_path, "wb") as f:
            f.write(r.content)
        img = Image.open(cache_path).convert("RGB")
        img = img.resize((1920, 1080), Image.LANCZOS)
        img.save(str(cache_path), "JPEG", quality=92)
        return str(cache_path)
    except Exception:
        return _create_placeholder_image(f"slide {index + 1}", index)


def _download_and_cache(url: str, cache_key: str, index: int) -> str:
    h = hashlib.md5(f"{cache_key}{index}".encode()).hexdigest()[:8]
    path = OUTPUT_DIR / f"img_{h}.jpg"
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


# ── Placeholder (offline fallback) ───────────────────────────────────────────

def _create_placeholder_image(query: str, index: int) -> str:
    """Vibrant gradient card — used only when fully offline."""
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
        r_ = int(dark[0] + (light[0] - dark[0]) * t)
        g_ = int(dark[1] + (light[1] - dark[1]) * t)
        b_ = int(dark[2] + (light[2] - dark[2]) * t)
        draw.line([(x, 0), (x, 1080)], fill=(r_, g_, b_))

    overlay = Image.new("RGB", (1920, 220), (0, 0, 0))
    img.paste(overlay, (0, 430))
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
    except Exception:
        font_lg = ImageFont.load_default()

    text = query[:70]
    bbox = draw.textbbox((0, 0), text, font=font_lg)
    draw.text(((1920 - (bbox[2] - bbox[0])) // 2, 460),
              text, fill=(255, 255, 255), font=font_lg)

    h = hashlib.md5(f"{query}{index}".encode()).hexdigest()[:8]
    path = OUTPUT_DIR / f"placeholder_{h}.jpg"
    img.save(str(path), "JPEG", quality=90)
    return str(path)


# ── Resize helper ─────────────────────────────────────────────────────────────

def _resize_for_aspect(path: str, aspect_ratio: str) -> str:
    ratios = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1":  (1080, 1080),
        "4:3":  (1440, 1080),
    }
    target_w, target_h = ratios.get(aspect_ratio, (1920, 1080))
    p = Path(path)
    out_path = p.parent / f"{p.stem}_{aspect_ratio.replace(':', 'x')}.jpg"

    # Duplicate prompts produce the same source path → same out_path, so
    # serialize on it and publish atomically to avoid concurrent corruption.
    with _key_lock(str(out_path)):
        if out_path.exists():
            return str(out_path)
        img = Image.open(path).convert("RGB")
        src_w, src_h = img.size
        if src_w / src_h > target_w / target_h:
            new_h = target_h
            new_w = int(src_w * (target_h / src_h))
        else:
            new_w = target_w
            new_h = int(src_h * (target_w / src_w))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        img  = img.crop((left, top, left + target_w, top + target_h))
        tmp_path = out_path.with_suffix(".tmp.jpg")
        img.save(str(tmp_path), "JPEG", quality=90)
        os.replace(str(tmp_path), str(out_path))
    return str(out_path)


# Public alias kept for any direct callers elsewhere in the codebase
def fetch_stock_image(query: str, index: int = 0) -> str | None:
    base_seed = int(hashlib.md5(query.encode()).hexdigest()[:6], 16) % 500
    return _fetch_stock_image(query, index, base_seed)
