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
    
    paths = []
    if media_path:
        raw_paths = media_path if isinstance(media_path, list) else [p.strip() for p in str(media_path).split(",") if p.strip()]
        paths = [Path(p) for p in raw_paths if Path(p).exists()]

    if paths:
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        files = {}
        file_handles = []
        try:
            for i, media_file in enumerate(paths):
                filename = media_file.name
                ext = media_file.suffix.lower()
                mime_type = mime_map.get(ext, "image/png")
                fh = open(media_file, "rb")
                file_handles.append(fh)
                files[f"files[{i}]"] = (filename, fh, mime_type)
                if i == 0:
                    payload["embeds"][0]["image"] = {"url": f"attachment://{filename}"}
                else:
                    payload["embeds"].append({"url": url, "image": {"url": f"attachment://{filename}"}})

            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                params={"wait": "true"},
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=30,
            )
        finally:
            for fh in file_handles:
                fh.close()
    else:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, params={"wait": "true"}, json=payload, timeout=30)

    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord said {resp.status_code}: {resp.text[:300]}")
    message_id = resp.json().get("id", "") if resp.content else ""
    return message_id, ""
