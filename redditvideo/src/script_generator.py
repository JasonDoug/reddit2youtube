import os
import re
from openai import OpenAI

PRESETS = {
    "YouTube Short": {
        "duration_sec": 60,
        "word_count": 120,
        "style": "energetic, punchy, hook in first 3 seconds",
        "aspect_ratio": "9:16",
        "platform": "YouTube Shorts",
    },
    "TikTok": {
        "duration_sec": 45,
        "word_count": 90,
        "style": "casual, trending, conversational",
        "aspect_ratio": "9:16",
        "platform": "TikTok",
    },
    "Instagram Reel": {
        "duration_sec": 30,
        "word_count": 60,
        "style": "visual, aspirational, quick cuts",
        "aspect_ratio": "9:16",
        "platform": "Instagram Reels",
    },
    "YouTube Long": {
        "duration_sec": 300,
        "word_count": 600,
        "style": "informative, engaging, detailed storytelling",
        "aspect_ratio": "16:9",
        "platform": "YouTube",
    },
    "Twitter/X Video": {
        "duration_sec": 60,
        "word_count": 100,
        "style": "bold, opinion-driven, shareable",
        "aspect_ratio": "16:9",
        "platform": "Twitter/X",
    },
    "Custom": {
        "duration_sec": 90,
        "word_count": 180,
        "style": "balanced, clear narration",
        "aspect_ratio": "16:9",
        "platform": "Generic",
    },
}


def get_openai_client() -> OpenAI:
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
    if base_url:
        return OpenAI(base_url=base_url, api_key=api_key)
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def generate_script(
    post: dict,
    preset_name: str,
    genre: str,
    custom_duration: int = 60,
    custom_style: str = "",
    extra_instructions: str = "",
) -> dict:
    preset = PRESETS.get(preset_name, PRESETS["Custom"]).copy()
    if preset_name == "Custom":
        preset["duration_sec"] = custom_duration
        preset["style"] = custom_style or preset["style"]

    word_count = preset["word_count"]
    duration = preset["duration_sec"]
    style = preset["style"]
    platform = preset["platform"]

    title = post.get("title", "")
    body = post.get("selftext", "")
    subreddit = post.get("subreddit", "")
    score = post.get("score", 0)

    system_prompt = f"""You are an expert viral content scriptwriter for {platform}.
Write scripts that are optimized for short-form video content.
Style: {style}
Always write in second/third person narrative voice, NOT as a Reddit post reader."""

    user_prompt = f"""Create a {genre} video script for {platform} based on this Reddit post.

Title: {title}
Subreddit: r/{subreddit}
Score: {score} upvotes
Content: {body[:500] if body else "(link post — use title only)"}

Requirements:
- Target duration: {duration} seconds (~{word_count} words)
- Genre: {genre}
- Style: {style}
- Must grab attention in the first 5 words
- Include a strong call to action at the end
{"- Additional instructions: " + extra_instructions if extra_instructions else ""}

Output format (use these exact headers):
HOOK:
[1-2 punchy opening sentences]

MAIN_SCRIPT:
[The full narration script]

CTA:
[Call to action]

IMAGE_PROMPTS:
[4-6 comma-separated visual scene descriptions for slideshow images, one per line, prefixed with "- "]"""

    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=1500,
    )

    raw = response.choices[0].message.content or ""

    hook = _extract_section(raw, "HOOK")
    main = _extract_section(raw, "MAIN_SCRIPT")
    cta = _extract_section(raw, "CTA")
    image_prompts_raw = _extract_section(raw, "IMAGE_PROMPTS")

    image_prompts = [
        line.lstrip("- ").strip()
        for line in image_prompts_raw.splitlines()
        if line.strip().lstrip("- ")
    ]

    full_script = f"{hook}\n\n{main}\n\n{cta}".strip()

    return {
        "hook": hook,
        "main_script": main,
        "cta": cta,
        "full_script": full_script,
        "image_prompts": image_prompts,
        "preset": preset_name,
        "genre": genre,
        "platform": platform,
        "target_duration_sec": duration,
        "aspect_ratio": preset["aspect_ratio"],
        "estimated_word_count": len(full_script.split()),
        "source_post_id": post.get("id", ""),
        "source_post_title": title,
    }


def _extract_section(text: str, header: str) -> str:
    pattern = rf"{header}:\s*\n(.*?)(?=\n[A-Z_]+:|$)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
