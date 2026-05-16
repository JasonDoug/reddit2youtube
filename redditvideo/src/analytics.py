import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "analytics.json"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_db() -> dict:
    if DB_PATH.exists():
        try:
            with open(DB_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"jobs": [], "stats": {"total_videos": 0, "total_scripts": 0, "total_searches": 0}}


def _save_db(db: dict):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


def log_search(subreddits: list[str], time_filter: str, result_count: int):
    db = _load_db()
    db["stats"]["total_searches"] = db["stats"].get("total_searches", 0) + 1
    db["jobs"].append({
        "type": "search",
        "subreddits": subreddits,
        "time_filter": time_filter,
        "result_count": result_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def log_script(post_title: str, platform: str, genre: str, word_count: int):
    db = _load_db()
    db["stats"]["total_scripts"] = db["stats"].get("total_scripts", 0) + 1
    db["jobs"].append({
        "type": "script",
        "post_title": post_title,
        "platform": platform,
        "genre": genre,
        "word_count": word_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def log_video(
    post_title: str,
    platform: str,
    genre: str,
    duration_sec: float,
    file_size_mb: float,
    video_path: str,
    audio_path: str,
    num_images: int,
    published: bool = False,
    publish_url: str = "",
):
    db = _load_db()
    db["stats"]["total_videos"] = db["stats"].get("total_videos", 0) + 1
    db["jobs"].append({
        "type": "video",
        "post_title": post_title,
        "platform": platform,
        "genre": genre,
        "duration_sec": round(duration_sec, 1),
        "file_size_mb": file_size_mb,
        "video_path": video_path,
        "audio_path": audio_path,
        "num_images": num_images,
        "published": published,
        "publish_url": publish_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def log_publish(video_path: str, platform: str, url: str, status: str):
    db = _load_db()
    db["jobs"].append({
        "type": "publish",
        "video_path": video_path,
        "platform": platform,
        "url": url,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_db(db)


def get_stats() -> dict:
    db = _load_db()
    jobs = db.get("jobs", [])

    searches = [j for j in jobs if j.get("type") == "search"]
    scripts = [j for j in jobs if j.get("type") == "script"]
    videos = [j for j in jobs if j.get("type") == "video"]
    publishes = [j for j in jobs if j.get("type") == "publish"]

    total_duration = sum(v.get("duration_sec", 0) for v in videos)
    total_size = sum(v.get("file_size_mb", 0) for v in videos)

    platform_counts: dict[str, int] = {}
    genre_counts: dict[str, int] = {}
    for v in videos:
        p = v.get("platform", "Unknown")
        g = v.get("genre", "Unknown")
        platform_counts[p] = platform_counts.get(p, 0) + 1
        genre_counts[g] = genre_counts.get(g, 0) + 1

    subreddit_counts: dict[str, int] = {}
    for s in searches:
        for sub in s.get("subreddits", []):
            subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

    recent_jobs = sorted(jobs, key=lambda x: x.get("timestamp", ""), reverse=True)[:20]

    return {
        "total_searches": len(searches),
        "total_scripts": len(scripts),
        "total_videos": len(videos),
        "total_publishes": len(publishes),
        "total_duration_sec": total_duration,
        "total_size_mb": round(total_size, 2),
        "platform_counts": platform_counts,
        "genre_counts": genre_counts,
        "subreddit_counts": subreddit_counts,
        "recent_jobs": recent_jobs,
        "all_videos": videos,
    }
