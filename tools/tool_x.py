"""X (Twitter) posting with tweepy, API v2."""
from pathlib import Path
import tweepy

from core import config


def configured():
    return all([config.X_API_KEY, config.X_API_SECRET, config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET])


def post_thread(tweets, media_path=None):
    """Posts tweets one by one, each as a reply to the last. Returns the tweet ids."""
    client = tweepy.Client(
        consumer_key=config.X_API_KEY,
        consumer_secret=config.X_API_SECRET,
        access_token=config.X_ACCESS_TOKEN,
        access_token_secret=config.X_ACCESS_TOKEN_SECRET,
    )
    media_ids = None
    if media_path and Path(media_path).exists():
        try:
            auth = tweepy.OAuth1UserHandler(
                config.X_API_KEY, config.X_API_SECRET, config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET
            )
            api = tweepy.API(auth)
            uploaded = api.media_upload(str(media_path))
            media_ids = [uploaded.media_id]
        except Exception as media_err:
            raise RuntimeError(f"Failed to upload media '{media_path}' to X: {media_err}") from media_err

    ids, reply_to = [], None
    for i, text in enumerate(tweets):
        try:
            kwargs = {"text": text, "in_reply_to_tweet_id": reply_to}
            if i == 0 and media_ids:
                kwargs["media_ids"] = media_ids
            resp = client.create_tweet(**kwargs)
        except Exception as e:
            err_str = str(e)
            if "402" in err_str or "credits depleted" in err_str.lower() or "credits" in err_str.lower():
                raise RuntimeError(
                    "X API monthly tweet quota reached / credits depleted (402 Payment Required). "
                    "Your free developer portal quota has been consumed for this billing cycle. "
                    "Wait for the monthly reset or upgrade your X developer tier."
                ) from e
            if "403" in err_str and any(w in err_str.lower() for w in ["usage", "cap", "limit", "credits"]):
                raise RuntimeError(
                    f"X API access limit reached (403 Forbidden: {e}). Free tier monthly tweet cap reached."
                ) from e
            raise RuntimeError(f"thread broke after {len(ids)} tweet(s) (ids so far: {ids}): {e}") from e
        reply_to = str(resp.data["id"])
        ids.append(reply_to)
    return ids


def thread_url(first_id):
    return f"https://x.com/i/status/{first_id}"
