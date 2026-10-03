"""LinkedIn posting (REST Posts API with fallback)."""
import requests

from core import config


def configured():
    return bool(config.LINKEDIN_ACCESS_TOKEN and config.LINKEDIN_PERSON_URN)


def post(text):
    """Makes a public text post using rest/posts with fallback to v2/ugcPosts. Returns (post_id, url)."""
    # 1. Try modern LinkedIn /rest/posts API
    rest_body = {
        "author": config.LINKEDIN_PERSON_URN,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    rest_headers = {
        "Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202401",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    resp = requests.post("https://api.linkedin.com/rest/posts", json=rest_body, headers=rest_headers, timeout=30)
    if resp.status_code in (200, 201):
        post_id = resp.headers.get("x-restli-id") or resp.headers.get("x-linkedin-id") or ""
        return post_id, f"https://www.linkedin.com/feed/update/{post_id}/"

    # 2. Fallback to /v2/ugcPosts if rest/posts is not available on this app/token
    ugc_body = {
        "author": config.LINKEDIN_PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    ugc_headers = {
        "Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    ugc_resp = requests.post("https://api.linkedin.com/v2/ugcPosts", json=ugc_body, headers=ugc_headers, timeout=30)
    if ugc_resp.status_code in (200, 201):
        post_id = ugc_resp.headers.get("x-restli-id") or ugc_resp.json().get("id", "")
        return post_id, f"https://www.linkedin.com/feed/update/{post_id}/"

    raise RuntimeError(f"LinkedIn post failed. REST ({resp.status_code}): {resp.text[:150]}; UGC ({ugc_resp.status_code}): {ugc_resp.text[:150]}")

