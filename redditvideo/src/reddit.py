import praw
import os
from datetime import datetime, timezone
from typing import Optional


def get_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "RedditVideoBot/1.0"),
    )


def fetch_top_posts(
    subreddits: list[str],
    time_filter: str = "week",
    limit: int = 10,
    min_score: int = 0,
    post_type: str = "all",
) -> list[dict]:
    """
    Fetch top posts from one or more subreddits.

    time_filter: hour, day, week, month, year, all
    post_type: all, text, link, image, video
    """
    reddit = get_reddit_client()
    results = []

    for sub_name in subreddits:
        sub_name = sub_name.strip().lstrip("r/").lstrip("/")
        try:
            subreddit = reddit.subreddit(sub_name)
            posts = subreddit.top(time_filter=time_filter, limit=limit)
            for post in posts:
                if post.score < min_score:
                    continue
                if post_type == "text" and not post.is_self:
                    continue
                if post_type == "link" and post.is_self:
                    continue
                if post_type == "image" and not any(
                    post.url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]
                ):
                    continue
                if post_type == "video" and not post.is_video:
                    continue

                created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                results.append(
                    {
                        "id": post.id,
                        "title": post.title,
                        "subreddit": sub_name,
                        "score": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "url": post.url,
                        "permalink": f"https://reddit.com{post.permalink}",
                        "is_self": post.is_self,
                        "selftext": post.selftext[:2000] if post.is_self else "",
                        "created_utc": created_dt.isoformat(),
                        "author": str(post.author) if post.author else "[deleted]",
                        "flair": post.link_flair_text or "",
                        "awards": post.total_awards_received,
                        "is_video": post.is_video,
                        "thumbnail": post.thumbnail if post.thumbnail not in ["self", "default", "nsfw", ""] else "",
                    }
                )
        except Exception as e:
            results.append({"error": str(e), "subreddit": sub_name})

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def fetch_hot_posts(subreddits: list[str], limit: int = 10) -> list[dict]:
    reddit = get_reddit_client()
    results = []
    for sub_name in subreddits:
        sub_name = sub_name.strip().lstrip("r/").lstrip("/")
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=limit):
                created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                results.append(
                    {
                        "id": post.id,
                        "title": post.title,
                        "subreddit": sub_name,
                        "score": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "url": post.url,
                        "permalink": f"https://reddit.com{post.permalink}",
                        "is_self": post.is_self,
                        "selftext": post.selftext[:2000] if post.is_self else "",
                        "created_utc": created_dt.isoformat(),
                        "author": str(post.author) if post.author else "[deleted]",
                        "flair": post.link_flair_text or "",
                        "awards": post.total_awards_received,
                        "is_video": post.is_video,
                        "thumbnail": post.thumbnail if post.thumbnail not in ["self", "default", "nsfw", ""] else "",
                    }
                )
        except Exception as e:
            results.append({"error": str(e), "subreddit": sub_name})

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def search_subreddits(query: str, limit: int = 5) -> list[str]:
    reddit = get_reddit_client()
    try:
        return [sub.display_name for sub in reddit.subreddits.search(query, limit=limit)]
    except Exception:
        return []
