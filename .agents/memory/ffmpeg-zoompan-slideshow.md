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
