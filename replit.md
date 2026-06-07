# Reddit Video Pipeline

A full content creation pipeline that turns top Reddit posts into viral short-form videos, complete with AI-generated scripts, voiceovers, Ken Burns-style slideshows, and optional YouTube upload.

## Run & Operate

- `cd redditvideo && streamlit run app.py --server.port 5000` — run the Streamlit dashboard
- The workflow "Reddit Video Pipeline" manages this automatically

## Stack

- Python 3.11 + Streamlit
- Reddit API: PRAW
- Script AI: OpenAI (via Replit AI Integrations — no key needed)
- Voiceover: gTTS (Google Text-to-Speech, free)
- Images: AI-generated (gpt-image-1 via Replit AI Integrations — default, matches the script subject), Unsplash/Pexels stock (add API keys), or styled placeholders
- Video assembly: FFmpeg + moviepy (Ken Burns zoompan filter)
- Analytics: JSON flat file (redditvideo/data/analytics.json)
- Charts: Plotly

## Where things live

- `redditvideo/app.py` — main Streamlit multi-page dashboard
- `redditvideo/src/reddit.py` — PRAW Reddit fetching
- `redditvideo/src/script_generator.py` — OpenAI script generation + PRESETS
- `redditvideo/src/voiceover.py` — gTTS voiceover generation
- `redditvideo/src/image_pipeline.py` — stock/placeholder image fetching + resizing
- `redditvideo/src/video_assembler.py` — FFmpeg video assembly with Ken Burns
- `redditvideo/src/analytics.py` — usage tracking + stats
- `redditvideo/src/youtube_uploader.py` — YouTube Data API v3 upload
- `redditvideo/output/` — generated videos, audio, images
- `redditvideo/data/analytics.json` — analytics database

## Architecture decisions

- Flat JSON analytics file for simplicity — no DB setup needed for a single-user tool
- FFmpeg's zoompan filter for Ken Burns effect — no Python video manipulation overhead
- gTTS used as free TTS; OpenAI TTS can be swapped in via voiceover.py
- OpenAI accessed via Replit AI Integrations proxy (no API key needed from user)
- YouTube upload is optional and uses a web-based OAuth2 flow (works on headless Replit; no server-side browser). The old `run_local_server` desktop flow does NOT work on Replit.
  - Requires YOUTUBE_CLIENT_SECRETS_JSON = the FULL JSON file (top-level `web` key) from a Google Cloud **Web application** OAuth client — not the bare `GOCSPX-...` client secret string.
  - The OAuth client must register the app's public URL (`https://<REPLIT_DOMAIN>/`) as an Authorized redirect URI.
  - User clicks "Connect YouTube account" in-app → authorizes in their own browser → Google redirects back with `?code=` → app exchanges it and stores `data/youtube_credentials.pkl`.

## Product

6-page Streamlit dashboard:
1. **Search Reddit** — search any subreddit(s), filter by time/score/type, select a post
2. **Script Generator** — AI-powered script with platform presets (YouTube Short, TikTok, Reel, etc.)
3. **Voiceover** — free gTTS narration with language + speed options
4. **Images** — Ken Burns slideshow images (AI-generated/stock/placeholder, auto-prompted from script). AI is the default and matches each slide to the script subject.
5. **Assemble Video** — FFmpeg-powered video assembly with download + YouTube upload
6. **Analytics** — usage charts, platform/genre breakdowns, recent activity log

## User preferences

- Free TTS preferred (gTTS)
- Both AI-generated and stock photos for images
- User has Reddit API credentials (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT)

## Gotchas

- Add UNSPLASH_ACCESS_KEY or PEXELS_API_KEY secret for real stock photos
- YouTube upload requires YOUTUBE_CLIENT_SECRETS_JSON (OAuth2 JSON from Google Cloud Console)
- Video assembly takes 1-3 minutes depending on number of images and video length
- FFmpeg must be installed (done via installSystemDependencies)

## Pointers

- See the `pnpm-workspace` skill for workspace structure (Node.js side)
- Python packages in redditvideo/requirements.txt
