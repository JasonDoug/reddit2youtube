"""
YouTube upload module.
Requires YOUTUBE_CLIENT_SECRET_JSON env var (path to OAuth2 client secret file)
and a one-time OAuth2 flow to generate credentials.
Falls back to a clear error message when not configured.
"""
import os
import json
import pickle
from pathlib import Path

CREDENTIALS_PATH = Path(__file__).parent.parent / "data" / "youtube_credentials.pkl"
CLIENT_SECRETS_PATH = Path(__file__).parent.parent / "data" / "client_secrets.json"


def is_youtube_configured() -> bool:
    return CLIENT_SECRETS_PATH.exists() or bool(os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON"))


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
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import google.auth.exceptions
    except ImportError:
        return {"error": "google-api-python-client not installed"}

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None

    if CREDENTIALS_PATH.exists():
        with open(CREDENTIALS_PATH, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        secrets_json = os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON", "")
        if secrets_json:
            CLIENT_SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CLIENT_SECRETS_PATH, "w") as f:
                f.write(secrets_json)

        if not CLIENT_SECRETS_PATH.exists():
            return {
                "error": "YouTube not configured. Please add your YOUTUBE_CLIENT_SECRETS_JSON "
                "secret (the content of your OAuth2 client secrets JSON file from Google Cloud Console)."
            }

        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_PATH), scopes)
        creds = flow.run_local_server(port=0)
        with open(CREDENTIALS_PATH, "wb") as f:
            pickle.dump(creds, f)

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
