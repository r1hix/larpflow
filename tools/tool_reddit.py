"""Reddit posting with PRAW."""
import praw

from core import config


def configured():
    return all([config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET, config.REDDIT_USERNAME, config.REDDIT_PASSWORD])


"""Reddit posting with PRAW."""
import praw

from core import config


def configured():
    return all([config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET, config.REDDIT_USERNAME, config.REDDIT_PASSWORD])


def post(subreddit, title, body, flair_text=None):
    """Makes one text post, automatically choosing or matching a flair if required. Returns (post_id, url)."""
    reddit = praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        username=config.REDDIT_USERNAME,
        password=config.REDDIT_PASSWORD,
        user_agent=config.REDDIT_USER_AGENT,
    )
    sub = reddit.subreddit(subreddit)

    # Check for link flair templates if the sub provides them
    flair_id = None
    try:
        templates = list(sub.flair.link_templates)
        if templates:
            # Try to match requested flair or common developer post tags
            target = (flair_text or "showcase,project,discussion,engineering,dev").lower().split(",")
            for tag in target:
                for t in templates:
                    if tag.strip() in t.get("text", "").lower():
                        flair_id = t.get("id")
                        break
                if flair_id:
                    break
            # If still none and sub requires flair, pick the first allowable template
            if not flair_id:
                flair_id = templates[0].get("id")
    except Exception:
        # User may not have permissions to query flairs or flair isn't mandatory
        pass

    kwargs = {"title": title, "selftext": body}
    if flair_id:
        kwargs["flair_id"] = flair_id

    submission = sub.submit(**kwargs)
    return submission.id, f"https://www.reddit.com{submission.permalink}"

