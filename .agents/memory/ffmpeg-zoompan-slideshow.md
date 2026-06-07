---
name: FFmpeg zoompan slideshow pitfall
description: Why a Ken Burns slideshow can collapse to the first image, and how to keep image + subtitle changes synced to slide beats
---

# FFmpeg zoompan multi-image slideshow

**Rule:** When building a per-image Ken Burns slideshow (one `zoompan` per image, then `concat`), each slide must be cut to an exact frame count, and one single frame-aligned `slide_dur` must drive the input `-t`, the zoompan length, AND the subtitle windows.

**Why:** `zoompan`'s `d=N` means "emit N output frames PER INPUT FRAME." Feeding it a looped still (`-loop 1 -t DUR -i img`) gives many input frames, so it emits `d * (many)` frames — slide 0 alone becomes hundreds of seconds. With `-shortest` tied to the audio, the whole video ends inside slide 0, so every visible frame is the FIRST image. (A plain `scale`+`concat` path without zoompan does not multiply frames, so it "works" and misleads you into thinking the images are the problem.)

**How to apply (per image):**
`[i:v]scale={2w}:{2h},zoompan=...:d={slide_frames}:s={w}x{h}:fps={fps},trim=duration={slide_dur},setpts=PTS-STARTPTS,setsar=1[vi]`
then `concat`. The `trim` is what caps each slide so zoompan's expansion can't bleed into later slides. `setpts=PTS-STARTPTS` normalizes timestamps for concat. Pre-`scale` to 2x for smooth sub-pixel pan.

`slide_frames = round(fps * per_image_duration)`, `slide_dur = slide_frames / fps`. Use this SAME `slide_dur` for subtitle `enable='between(t, i*slide_dur, (i+1)*slide_dur)'` so captions change on the exact same beat as the image. Do NOT add a separate `transition_duration` to the input `-t` unless an actual xfade is implemented — it just desyncs captions from images.

**Edge case (pre-existing, accepted):** `per_image_duration = max(audio/n, 2.0)` can make total slideshow length differ from audio length; `-shortest` may then truncate the last slide/caption or trailing audio. Only matters for very short audio + many images.

## Word-level karaoke captions (genre fonts + pop)
- Captions render word-by-word via one `drawtext` per word using `textfile=` (path in the filtergraph, text isolated in a temp file — no escaping of the graph needed). In textfile mode the content is literal except `\` escapes and `%{...}` expansion, so only escape `\` and `%`; do NOT escape `:` (it would print a literal backslash).
- gTTS has no word timestamps: estimate each word's start by weighting word length (`len(alnum)+2`) across the render duration.
- **Time captions over `min(audio_duration, n*slide_dur)`**, not the slideshow length. `-shortest` cuts the output to the shorter stream; timing over the longer one drops the final words when `per_image_duration` is clamped to its 2.0s floor (many images / short audio).
- A "pop" zoom = two drawtext per word (bigger for ~0.1s, then base). That doubles filter count; cap it (drop pop above ~280 words) so long scripts don't explode into thousands of filters and stall the encode.
- Hundreds of drawtext filters exceed argv limits — write the whole filtergraph to a file and use `-filter_complex_script` instead of `-filter_complex`.
- Genre→font/colour map lives in video_assembler `_GENRE_STYLES`; TTFs are bundled in `redditvideo/assets/fonts/` (Bangers/Anton/Pacifico/BebasNeue/Creepster) with DejaVu fallback.

## Subject-relevant slideshow images
- Picsum (`/seed/...`) returns RANDOM photos unrelated to the topic — only a last-resort fallback, never the default. To match the script subject, generate images from the script's `image_prompts`.
- Runtime AI image generation in Python uses the SAME Replit OpenAI proxy as the script step: `OpenAI(base_url=AI_INTEGRATIONS_OPENAI_BASE_URL, api_key=AI_INTEGRATIONS_OPENAI_API_KEY)`, model `gpt-image-1`, which returns `b64_json` (not a URL). No user API key needed. (The agent-side `generateImage` skill tool is NOT callable at app runtime.)
- gpt-image-1 only accepts sizes 1024x1024 / 1536x1024 / 1024x1536 — map aspect to nearest then crop with the existing resize helper.
- Generation is slow (~15-40s/image); run slides concurrently with ThreadPoolExecutor since calls are independent. Cache by md5(prompt|size).
- Concurrency hazard: duplicate prompts in one batch map to the SAME cache file → threads race on a half-written file. Guard with a per-cache-key `threading.Lock` + atomic publish (write `.tmp` then `os.replace`). Same applies to the resized-output path.

## Word-caption sync without timestamps (gTTS)
- gTTS exposes no word timestamps, so caption sync is a heuristic. Pure letter-count weighting drifts on punctuation-heavy scripts because the TTS voice PAUSES at punctuation.
- Fix that generalizes across scripts: weight each word `len(alnum)+2` PLUS a pause weight added to the word it follows — sentence-enders (`. ! ? … : ;`) ≈ +7, comma/dash (`, — -`) ≈ +4. This both delays following words and lets the punctuated word linger on screen through the pause.
- Distribute starts over `effective_duration` (≈ audio length); the per-image-duration 2.0s floor only ever raises slide_dur, so total_video ≥ audio and effective≈audio in practice.
