"""Discord webhook dev-log (rich embed)."""
import requests

from core import config


def configured():
    return bool(config.DISCORD_WEBHOOK_URL)


def post(title, body, url):
    """Sends an embed. Returns (message_id, "")."""
    payload = {"embeds": [{"title": title[:256], "description": body[:4000], "url": url, "color": 0x5865F2}]}
    resp = requests.post(config.DISCORD_WEBHOOK_URL, params={"wait": "true"}, json=payload, timeout=30)
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord said {resp.status_code}: {resp.text[:300]}")
    message_id = resp.json().get("id", "") if resp.content else ""
    return message_id, ""
