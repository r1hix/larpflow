"""History. Everything is saved in storage/history.sqlite."""
import json
import sqlite3
import time
from contextlib import closing

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    problem TEXT,
    solution TEXT,
    drafts_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    ok INTEGER NOT NULL,
    post_id TEXT,
    url TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def _connect():
    config.STORAGE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(config.STORAGE_DIR / "history.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _exec(sql, args=()):
    with closing(_connect()) as conn:
        with conn:  # commits when the block ends
            return conn.execute(sql, args).lastrowid


def _query(sql, args=()):
    with closing(_connect()) as conn:
        return [dict(row) for row in conn.execute(sql, args).fetchall()]


def save_draft(repo, problem, solution, drafts_dict):
    return _exec(
        "INSERT INTO drafts (repo, problem, solution, drafts_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (repo, problem, solution, json.dumps(drafts_dict), _now()),
    )


def get_draft(draft_id):
    rows = _query("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    if not rows:
        return None
    row = rows[0]
    row["drafts"] = json.loads(row.pop("drafts_json"))
    return row


def update_drafts(draft_id, drafts_dict):
    _exec("UPDATE drafts SET drafts_json = ? WHERE id = ?", (json.dumps(drafts_dict), draft_id))


def set_status(draft_id, status):
    _exec("UPDATE drafts SET status = ? WHERE id = ?", (status, draft_id))


def log_post(draft_id, platform, ok, post_id="", url="", detail=""):
    _exec(
        "INSERT INTO posts (draft_id, platform, ok, post_id, url, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (draft_id, platform, 1 if ok else 0, post_id, url, detail, _now()),
    )


def posted_platforms(draft_id):
    """Platforms that already got this draft. Stops double posting on retry."""
    rows = _query("SELECT DISTINCT platform FROM posts WHERE draft_id = ? AND ok = 1", (draft_id,))
    return {row["platform"] for row in rows}


def post_links(draft_id):
    return _query("SELECT platform, url FROM posts WHERE draft_id = ? AND ok = 1", (draft_id,))


def past_for_repo(repo, limit=3):
    """Short text about what was already posted for this repo, so we don't repeat it."""
    rows = _query(
        "SELECT * FROM drafts WHERE repo = ? AND status IN ('posted', 'partial') ORDER BY id DESC LIMIT ?",
        (repo, limit),
    )
    lines = []
    for row in rows:
        d = json.loads(row["drafts_json"])
        first_tweet = d["tweets"][0] if d.get("tweets") else ""
        lines.append(f"- {row['created_at']}: problem was '{row['problem']}'. First tweet: {first_tweet}")
    return "\n".join(lines)


def recent_history(limit=10):
    return _query(
        """SELECT d.id, d.repo, d.status, d.created_at,
                  (SELECT group_concat(platform) FROM posts p WHERE p.draft_id = d.id AND p.ok = 1) AS platforms
           FROM drafts d ORDER BY d.id DESC LIMIT ?""",
        (limit,),
    )
