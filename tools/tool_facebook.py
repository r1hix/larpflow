"""Facebook posting via Graph API."""
import requests

from core import config


def configured():
    return bool(config.FACEBOOK_PAGE_ID and config.FACEBOOK_ACCESS_TOKEN)


def post(text):
    """Makes a post to a Facebook Page via Graph API. Returns (post_id, url)."""
    url = f"https://graph.facebook.com/v19.0/{config.FACEBOOK_PAGE_ID}/feed"
    payload = {
        "message": text,
        "access_token": config.FACEBOOK_ACCESS_TOKEN,
    }
    resp = requests.post(url, data=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Facebook Graph API said {resp.status_code}: {resp.text[:300]}")
    post_id = resp.json().get("id", "")
    return post_id, f"https://www.facebook.com/{post_id}"
