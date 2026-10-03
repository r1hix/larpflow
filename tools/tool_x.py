"""X (Twitter) posting with tweepy, API v2."""
import tweepy

from core import config


def configured():
    return all([config.X_API_KEY, config.X_API_SECRET, config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET])


def post_thread(tweets):
    """Posts tweets one by one, each as a reply to the last. Returns the tweet ids."""
    client = tweepy.Client(
        consumer_key=config.X_API_KEY,
        consumer_secret=config.X_API_SECRET,
        access_token=config.X_ACCESS_TOKEN,
        access_token_secret=config.X_ACCESS_TOKEN_SECRET,
    )
    ids, reply_to = [], None
    for text in tweets:
        try:
            resp = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
        except Exception as e:
            raise RuntimeError(f"thread broke after {len(ids)} tweet(s) (ids so far: {ids}): {e}") from e
        reply_to = str(resp.data["id"])
        ids.append(reply_to)
    return ids


def thread_url(first_id):
    return f"https://x.com/i/status/{first_id}"
