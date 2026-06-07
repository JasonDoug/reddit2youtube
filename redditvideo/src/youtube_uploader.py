"""
YouTube upload module using a web-based OAuth2 flow (works on headless Replit).

Setup (one-time, done by the user in Google Cloud Console):
  1. Enable "YouTube Data API v3".
  2. Create OAuth2 credentials of type **Web application**.
  3. Add this app's URL as an Authorized redirect URI (see redirect_uri()).
  4. Download the JSON and paste its FULL contents into the
     YOUTUBE_CLIENT_SECRETS_JSON secret.

After that, the user clicks "Connect YouTube account" in the app, authorises in
their own browser, and Google redirects back here with a code we exchange for
credentials. No server-side browser is needed.

Notes:
  - The OAuth redirect creates a *new* Streamlit session, so the anti-CSRF
    `state` is persisted to a small file (not session_state) and validated on
    return.
  - Credentials are stored as JSON (via Credentials.to_json) rather than pickle
    to avoid unsafe deserialization.
"""
import os
import json
import time
from pathlib import Path

# Google may return a superset of the requested scopes (e.g. with
# include_granted_scopes); relax oauthlib so that doesn't raise.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

_DATA_DIR = Path(__file__).parent.parent / "data"
CREDENTIALS_PATH = _DATA_DIR / "youtube_credentials.json"
STATE_PATH = _DATA_DIR / "yt_oauth_states.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_STATE_TTL = 600  # seconds an issued OAuth state stays valid


# ── Configuration helpers ───────────────────────────────────────────────────
def redirect_uri() -> str:
    """The public app URL Google must redirect back to (must be registered).

    In this workspace the domain root ('/') is served by another service, while
    the Streamlit app is exposed on port 5000. So the redirect must target
    :5000. An explicit YOUTUBE_OAUTH_REDIRECT_URI env var overrides everything
    (useful for a published deployment where the app is served at '/').
    """
    override = os.environ.get("YOUTUBE_OAUTH_REDIRECT_URI", "").strip()
    if override:
        return override
    domains = os.environ.get("REPLIT_DOMAINS", "")
    domain = domains.split(",")[0].strip() if domains else ""
    if not domain:
        domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    return f"https://{domain}:5000/" if domain else ""


def _client_config() -> dict | None:
    """Parse YOUTUBE_CLIENT_SECRETS_JSON into a valid client-config dict or None."""
    raw = os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON", "").strip()
    if not raw:
        return None
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(cfg, dict) or ("web" not in cfg and "installed" not in cfg):
        return None
    return cfg


def config_problem() -> str | None:
    """Return a code describing why config is invalid, or None if it's OK.

    Codes: 'missing', 'not_json', 'wrong_shape', 'not_web'.
    """
    raw = os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON", "").strip()
    if not raw:
        return "missing"
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError:
        return "not_json"
    if not isinstance(cfg, dict) or ("web" not in cfg and "installed" not in cfg):
        return "wrong_shape"
    if "web" not in cfg:
        return "not_web"
    return None


def is_youtube_configured() -> bool:
    """True when a structurally valid client secrets JSON is present."""
    return _client_config() is not None


# ── Anti-CSRF state store (survives the redirect's new session) ─────────────
def _read_states() -> list[dict]:
    if not STATE_PATH.exists():
        return []
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_states(states: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(states, f)


def _store_state(state: str) -> None:
    now = time.time()
    states = [s for s in _read_states() if now - s.get("ts", 0) < _STATE_TTL]
    states.append({"state": state, "ts": now})
    _write_states(states)


def _consume_state(state: str) -> bool:
    """Return True if `state` was issued and unexpired; remove it either way."""
    if not state:
        return False
    now = time.time()
    states = [s for s in _read_states() if now - s.get("ts", 0) < _STATE_TTL]
    matched = any(s.get("state") == state for s in states)
    _write_states([s for s in states if s.get("state") != state])
    return matched


# ── Credential storage (JSON, not pickle) ───────────────────────────────────
def _load_creds():
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_file(str(CREDENTIALS_PATH), SCOPES)
    except Exception:
        return None


def _save_creds(creds) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CREDENTIALS_PATH, "w") as f:
        f.write(creds.to_json())


def _valid_creds():
    """Return valid credentials (refreshing if needed) or None."""
    from google.auth.transport.requests import Request

    creds = _load_creds()
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_creds(creds)
        except Exception:
            return None
    if creds and creds.valid:
        return creds
    return None


def is_authenticated() -> bool:
    """True when we hold valid (or refreshable) credentials."""
    try:
        return _valid_creds() is not None
    except ImportError:
        return False


def disconnect() -> None:
    """Forget stored credentials so the user can reconnect."""
    if CREDENTIALS_PATH.exists():
        CREDENTIALS_PATH.unlink()


# ── Web OAuth flow ──────────────────────────────────────────────────────────
def get_auth_url() -> dict:
    """Build the Google consent URL. Returns {auth_url, redirect_uri} or {error}."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return {"error": "google-auth-oauthlib not installed"}

    cfg = _client_config()
    if cfg is None:
        return {"error": "YouTube client secrets JSON missing or invalid."}
    redirect = redirect_uri()
    if not redirect:
        return {"error": "Could not determine this app's public URL for the redirect."}

    try:
        flow = Flow.from_client_config(cfg, scopes=SCOPES, redirect_uri=redirect)
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        _store_state(state)
    except Exception as e:
        return {"error": f"Could not build authorization URL: {e}"}
    return {"auth_url": auth_url, "redirect_uri": redirect}


def finish_auth(code: str, state: str = "") -> dict:
    """Validate state, exchange the authorization code for credentials, store them."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return {"error": "google-auth-oauthlib not installed"}

    if not _consume_state(state):
        return {"error": "Security check failed (invalid or expired request). Please click Connect again."}

    cfg = _client_config()
    if cfg is None:
        return {"error": "YouTube client secrets JSON missing or invalid."}
    redirect = redirect_uri()
    try:
        flow = Flow.from_client_config(cfg, scopes=SCOPES, redirect_uri=redirect)
        flow.fetch_token(code=code)
    except Exception as e:
        return {"error": f"Authorization failed: {e}"}

    creds = flow.credentials
    _save_creds(creds)
    if not getattr(creds, "refresh_token", None):
        # Without a refresh token, access expires in ~1 hour with no renewal.
        return {"success": True, "warning": "Connected, but Google didn't return a long-term token. "
                "Uploads may stop working after ~1 hour — disconnect and reconnect to fix."}
    return {"success": True}


# ── Upload ──────────────────────────────────────────────────────────────────
def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "22",
    privacy: str = "private",
) -> dict:
    """Upload a video to YouTube. Returns dict with url or error."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return {"error": "google-api-python-client not installed"}

    try:
        creds = _valid_creds()
    except ImportError:
        return {"error": "google-auth libraries not installed"}
    if not creds:
        return {"error": "Not connected to YouTube — click 'Connect YouTube account' first."}

    try:
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:500],
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy},
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)
        response = request.execute()
        video_id = response.get("id", "")
        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title,
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_video_stats(video_id: str) -> dict:
    """Fetch view / like / comment counts for a video via the YouTube Data API."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {"error": "google-api-python-client not installed"}

    try:
        creds = _valid_creds()
    except ImportError:
        return {"error": "google-auth libraries not installed"}
    if not creds:
        return {"error": "Not authenticated — connect your YouTube account first."}

    try:
        youtube = build("youtube", "v3", credentials=creds)
        resp = youtube.videos().list(part="statistics", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return {"error": f"Video {video_id} not found or not yet public"}

        stats = items[0]["statistics"]
        return {
            "views":    int(stats.get("viewCount",    0)),
            "likes":    int(stats.get("likeCount",    0)),
            "comments": int(stats.get("commentCount", 0)),
        }
    except Exception as e:
        return {"error": str(e)}
