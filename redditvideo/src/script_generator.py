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

PROVIDERS = {
    "OpenAI (Replit)": "openai_replit",
    "OpenRouter (Replit)": "openrouter_replit",
    "Ollama Cloud": "ollama_cloud",
}

OPENROUTER_MODELS = [
    # Meta Llama
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    # Mistral
    "mistralai/mistral-large-2512",
    "mistralai/mistral-medium-3",
    "mistralai/mistral-small-3.2-24b-instruct",
    "mistralai/mixtral-8x22b-instruct",
    # DeepSeek
    "deepseek/deepseek-chat-v3.1",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-flash:free",
    # Qwen
    "qwen/qwen3-235b-a22b",
    "qwen/qwen3-32b",
    "qwen/qwen3-14b",
    "qwen/qwen-2.5-72b-instruct",
    # Google Gemma
    "google/gemma-3-27b-it",
    "google/gemma-4-31b-it",
    "google/gemma-4-31b-it:free",
    # Cohere
    "cohere/command-a",
    "cohere/command-r-plus-08-2024",
    # xAI
    "x-ai/grok-4.3",
    # Microsoft
    "microsoft/phi-4",
    # Nvidia
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
]

OPENAI_REPLIT_MODELS = [
    "gpt-5.4",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
]


def get_client(provider_key: str, ollama_base_url: str = "", ollama_api_key: str = "") -> tuple[OpenAI, str]:
    """
    Returns (OpenAI-compatible client, provider_label).
    All three providers use the OpenAI SDK — they only differ in base_url and api_key.
    """
    if provider_key == "openrouter_replit":
        base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "")
        api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "dummy")
        if not base_url:
            raise EnvironmentError("AI_INTEGRATIONS_OPENROUTER_BASE_URL is not set. OpenRouter integration may not be provisioned.")
        return OpenAI(base_url=base_url, api_key=api_key), "OpenRouter"

    if provider_key == "ollama_cloud":
        base_url = ollama_base_url or os.environ.get("OLLAMA_CLOUD_BASE_URL", "")
        api_key = ollama_api_key or os.environ.get("OLLAMA_CLOUD_API_KEY", "ollama")
        if not base_url:
            raise EnvironmentError(
                "Ollama Cloud base URL is not configured. Enter it in the provider settings "
                "or set OLLAMA_CLOUD_BASE_URL as a secret."
            )
        return OpenAI(base_url=base_url, api_key=api_key), "Ollama Cloud"

    # Default: OpenAI via Replit AI Integrations
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
    if base_url:
        return OpenAI(base_url=base_url, api_key=api_key), "OpenAI (Replit)"
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "")), "OpenAI"


def _pick_max_tokens_param(provider_key: str, model: str) -> dict:
    """
    OpenAI gpt-5+ models use max_completion_tokens; everything else uses max_tokens.
    """
    if provider_key == "openai_replit" and model.startswith("gpt-5"):
        return {"max_completion_tokens": 1500}
    return {"max_tokens": 1500}


def generate_script(
    post: dict,
    preset_name: str,
    genre: str,
    custom_duration: int = 60,
    custom_style: str = "",
    extra_instructions: str = "",
    provider: str = "openai_replit",
    model: str = "gpt-5.2",
    ollama_base_url: str = "",
    ollama_api_key: str = "",
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
[4-6 visual scene descriptions for slideshow images, one per line, prefixed with "- "]"""

    client, provider_label = get_client(provider, ollama_base_url, ollama_api_key)
    token_param = _pick_max_tokens_param(provider, model)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        **token_param,
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
        "provider": provider_label,
        "model": model,
    }


def _extract_section(text: str, header: str) -> str:
    pattern = rf"{header}:\s*\n(.*?)(?=\n[A-Z_]+:|$)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
