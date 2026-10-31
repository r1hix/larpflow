"""LinkedIn posting (REST Posts API with fallback and image upload)."""
from pathlib import Path
import requests

from core import config


def configured():
    return bool(config.LINKEDIN_ACCESS_TOKEN and config.LINKEDIN_PERSON_URN)


def _upload_image_v2(image_path):
    """Registers and uploads an image asset to LinkedIn v2 API. Returns asset URN or None."""
    try:
        headers = {
            "Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": config.LINKEDIN_PERSON_URN,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        reg_resp = requests.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if reg_resp.status_code not in (200, 201):
            return None
        val = reg_resp.json().get("value", {})
        upload_url = (
            val.get("uploadMechanism", {})
            .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
            .get("uploadUrl")
        )
        asset_urn = val.get("asset")
        if not upload_url or not asset_urn:
            return None

        with open(image_path, "rb") as f:
            up_headers = {"Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}"}
            up_resp = requests.put(upload_url, data=f, headers=up_headers, timeout=60)
            if up_resp.status_code not in (200, 201):
                return None

        return asset_urn
    except Exception:
        return None


def post(text, media_path=None):
    """Makes a public post using rest/posts with fallback to v2/ugcPosts. Supports optional image media (single or multi-image)."""
    paths = []
    if media_path:
        if isinstance(media_path, (list, tuple)):
            for p in media_path:
                if p and Path(p).exists():
                    paths.append(Path(p))
        elif isinstance(media_path, str):
            for part in media_path.split(","):
                part = part.strip()
                if part and Path(part).exists():
                    paths.append(Path(part))

    asset_urns = []
    for p in paths:
        urn = _upload_image_v2(str(p))
        if urn:
            asset_urns.append((urn, p.stem))

    # 1. Try modern LinkedIn /rest/posts API if no image
    if not asset_urns:
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
        try:
            resp = requests.post("https://api.linkedin.com/rest/posts", json=rest_body, headers=rest_headers, timeout=30)
            if resp.status_code in (200, 201):
                post_id = resp.headers.get("x-restli-id") or resp.headers.get("x-linkedin-id") or ""
                return post_id, f"https://www.linkedin.com/feed/update/{post_id}/"
        except Exception:
            pass

    # 2. UGC API (v2/ugcPosts) supporting image attachment (single or multi-image) or text fallback
    ugc_content = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": "IMAGE" if asset_urns else "NONE",
    }
    if asset_urns:
        ugc_content["media"] = [
            {
                "status": "READY",
                "description": {"text": stem},
                "media": urn,
                "title": {"text": stem},
            }
            for urn, stem in asset_urns
        ]

    ugc_body = {
        "author": config.LINKEDIN_PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": ugc_content},
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

    raise RuntimeError(f"LinkedIn post failed. UGC ({ugc_resp.status_code}): {ugc_resp.text[:200]}")
