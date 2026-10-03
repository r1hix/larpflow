"""Loads settings from .env and the config/ folder."""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STORAGE_DIR = ROOT / "storage"

load_dotenv(ROOT / ".env")


def env(name, default=""):
    return os.getenv(name, default).strip()


def env_bool(name, default=False):
    value = env(name)
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "y", "on")


# safety switch. True means nothing really gets posted.
DRY_RUN = env_bool("DRY_RUN", True)

LLM_API_KEY = env("LLM_API_KEY")
LLM_BASE_URL = env("LLM_BASE_URL")
LLM_MODEL = env("LLM_MODEL", "gpt-4o-mini")

GITHUB_USER = env("GITHUB_USER", "r1hix")
GITHUB_TOKEN = env("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    try:
        import subprocess
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            GITHUB_TOKEN = res.stdout.strip()
    except Exception:
        pass


TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_OWNER_ID = int(env("TELEGRAM_OWNER_ID", "0") or 0)

X_API_KEY = env("X_API_KEY")
X_API_SECRET = env("X_API_SECRET")
X_ACCESS_TOKEN = env("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = env("X_ACCESS_TOKEN_SECRET")

REDDIT_CLIENT_ID = env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = env("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = env("REDDIT_USERNAME")
REDDIT_PASSWORD = env("REDDIT_PASSWORD")
REDDIT_USER_AGENT = env("REDDIT_USER_AGENT", "larpflow")
REDDIT_ALLOWED_SUBS = [
    s.strip().replace("r/", "")
    for s in env("REDDIT_ALLOWED_SUBS", "SideProject").split(",")
    if s.strip()
]

LINKEDIN_ACCESS_TOKEN = env("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_URN = env("LINKEDIN_PERSON_URN")

DISCORD_WEBHOOK_URL = env("DISCORD_WEBHOOK_URL")


def load_persona():
    return json.loads((CONFIG_DIR / "persona.json").read_text(encoding="utf-8"))


def load_system_prompt():
    return (CONFIG_DIR / "system_instructions.md").read_text(encoding="utf-8")


def load_linkedin_profile():
    """Returns the pasted LinkedIn text, or "" if the file is still empty."""
    path = CONFIG_DIR / "linkedin_profile.md"
    if not path.exists():
        return ""
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    body = "\n".join(
        line for line in text.splitlines() if line.strip() and not line.startswith("#")
    )
    return text.strip() if body.strip() else ""
