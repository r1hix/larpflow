"""Discord webhook dev-log (rich embed)."""
import json
from pathlib import Path
import requests

from core import config


def configured():
    return bool(config.DISCORD_WEBHOOK_URL)


def post(title, body, url, media_path=None):
    """Sends an embed with optional image. Returns (message_id, "")."""
    payload = {"embeds": [{"title": title[:256], "description": body[:4000], "url": url, "color": 0x5865F2}]}
    
    if media_path and Path(media_path).exists():
        filename = Path(media_path).name
        payload["embeds"][0]["image"] = {"url": f"attachment://{filename}"}
        with open(media_path, "rb") as f:
            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                params={"wait": "true"},
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (filename, f, "image/png")},
                timeout=30,
            )
    else:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, params={"wait": "true"}, json=payload, timeout=30)

    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord said {resp.status_code}: {resp.text[:300]}")
    message_id = resp.json().get("id", "") if resp.content else ""
    return message_id, ""
