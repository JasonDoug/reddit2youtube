# Reddit Video Pipeline

A full content creation pipeline that turns top Reddit posts into viral short-form videos, complete with AI-generated scripts, voiceovers, Ken Burns-style slideshows, and optional YouTube upload.

## What It Does

1. **Search Reddit** — find hot/top posts from any subreddit(s)
2. **Script Generator** — AI writes a platform-optimized script (YouTube Short, TikTok, Reel, etc.)
3. **Voiceover** — free text-to-speech narration with language and speed options
4. **Images** — auto-generated slideshow images (AI-generated, stock photos, or placeholders)
5. **Assemble Video** — FFmpeg-powered video with Ken Burns zoom/pan effect
6. **YouTube Upload** — one-click publish to your channel
7. **Analytics** — track what you've generated and published

## Prerequisites

- **Python 3.11+**
- **FFmpeg** (required for video assembly)
- **Git** (for cloning)

### Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/JasonDoug/reddit2youtube.git
cd reddit2youtube/redditvideo
```

### 2. Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate       # macOS/Linux
# OR
venv\Scripts\activate          # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

Create a file named `.env` in the `redditvideo/` directory:

```bash
# Required: Reddit API credentials
# Get these from https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_app_name_by_your_username

# Required for local development: OpenAI API key
# The Replit AI proxy only works inside Replit; locally you need your own key
OPENAI_API_KEY=sk-your_openai_key

# Optional: YouTube upload
# Full JSON from Google Cloud Console OAuth client (Web application type)
YOUTUBE_CLIENT_SECRETS_JSON='{"web":{"client_id":"...","client_secret":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":["http://localhost:5000/"]}}'

# For local development, override the redirect URI
YOUTUBE_OAUTH_REDIRECT_URI=http://localhost:5000/

# Optional: stock photo API keys
UNSPLASH_ACCESS_KEY=your_unsplash_key
PEXELS_API_KEY=your_pexels_key
```

**How to get each credential:**

- **Reddit API**: Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → create a "script" app
- **OpenAI API**: Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **YouTube OAuth**: Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Web application) → add `http://localhost:5000/` as Authorized redirect URI
- **Unsplash API**: [unsplash.com/developers](https://unsplash.com/developers)
- **Pexels API**: [pexels.com/api](https://www.pexels.com/api/)

## Run the App

```bash
streamlit run app.py --server.port 5000
```

Open your browser to: **http://localhost:5000**

## Project Structure

```
redditvideo/
├── app.py                    # Main Streamlit dashboard
├── requirements.txt          # Python dependencies
├── src/
│   ├── reddit.py            # PRAW Reddit fetching
│   ├── script_generator.py  # AI script generation
│   ├── voiceover.py         # gTTS voiceover
│   ├── image_pipeline.py    # Image fetching/resizing
│   ├── video_assembler.py   # FFmpeg video assembly
│   ├── analytics.py         # Usage tracking
│   └── youtube_uploader.py  # YouTube OAuth + upload
├── data/
│   ├── analytics.json       # Usage statistics
│   └── yt_oauth_states.json # OAuth state store (auto-created)
└── output/                  # Generated videos, audio, images
```

## Key Differences from Replit

| Feature | Replit | Local |
|---------|--------|-------|
| OpenAI API | Uses Replit AI proxy (no key needed) | Requires `OPENAI_API_KEY` |
| AI Image Generation | Uses Replit AI proxy | Requires OpenAI API key |
| YouTube Redirect URI | `https://...replit.dev:5000/` | `http://localhost:5000/` |
| Secrets | Managed via Replit Secrets panel | `.env` file |

## Troubleshooting

### "YouTube authorization failed: redirect_uri_mismatch"

In Google Cloud Console, make sure your OAuth client's **Authorized redirect URI** is exactly `http://localhost:5000/` (with trailing slash). It must match your `YOUTUBE_OAUTH_REDIRECT_URI` env var character-for-character.

### "No images generated"

Check that `OPENAI_API_KEY` is set. AI image generation requires it. As a fallback, set `UNSPLASH_ACCESS_KEY` or `PEXELS_API_KEY` to use stock photos instead.

### "Video assembly failed"

Make sure FFmpeg is installed and on your PATH:
```bash
ffmpeg -version
```

### "Python module not found"

Make sure your virtual environment is activated:
```bash
source venv/bin/activate       # macOS/Linux
# or
venv\Scripts\activate          # Windows
```

## Stack

- **Python 3.11 + Streamlit** — UI framework
- **PRAW** — Reddit API
- **OpenAI** — Script generation and image generation
- **gTTS** — Free text-to-speech
- **FFmpeg** — Video assembly (Ken Burns zoompan)
- **Plotly** — Analytics charts
- **Google OAuth2** — YouTube upload

## User Preferences

- Free TTS preferred (gTTS)
- AI-generated images as default, stock photos as fallback
- Reddit API credentials required for post search

## License

MIT
