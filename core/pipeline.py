"""The flow: ingest -> draft -> (human approves) -> dispatch. Used by the bot and the CLI."""
from . import config, db, drafts
from tools import tool_discord, tool_facebook, tool_github, tool_linkedin, tool_reddit, tool_x



def parse_run_args(text):
    parts = [p.strip() for p in text.split("|", 2)]
    if len(parts) == 1 and parts[0]:
        return parts[0], "", ""
    if len(parts) != 3 or not all(parts):
        raise ValueError("Use it like this:\nlarpflow run repo-name\nor: larpflow run 'repo-name | problem | solution'")
    return parts


def make_drafts(repo, problem="", solution="", commit_count=10, post_type="auto", media_path=""):
    """Agent 1 + Agent 2. Returns (draft_id, repo_info, drafts)."""
    info = tool_github.inspect_repo(repo, commit_count=commit_count)
    past = db.past_for_repo(info["full_name"])

    # If problem/solution are omitted, infer them from the latest commit & diff
    if not problem or not solution:
        commits = info.get("recent_commits", [])
        if commits:
            top_msg = commits[0].get("message", "")
            patches = []
            for ch in commits[0].get("changed", []):
                if ch.get("patch"):
                    patches.append(f"File {ch['file']}:\n{ch['patch'][:400]}")
            patch_summary = "\n".join(patches)[:1000]

            problem = f"Issue addressed in commit '{top_msg}'"
            solution = f"Changes in commit {commits[0].get('sha', '')}: {patch_summary or top_msg}"
        else:
            problem = f"Core architecture and challenges in {repo}"
            solution = f"Implementation details and trade-offs of {repo}"

    d = drafts.generate(info, problem, solution, past, post_type=post_type)
    detected_img = media_path or _find_image(repo)
    if detected_img and (not d.visual_asset or not d.visual_asset.startswith("http")):
        d.visual_asset = str(detected_img)

    draft_id = db.save_draft(info["full_name"], problem, solution, d.model_dump())
    return draft_id, info, d




def make_profile_readme():
    repos = tool_github.list_repos()
    text = drafts.generate_profile_readme(repos)
    config.STORAGE_DIR.mkdir(exist_ok=True)
    path = config.STORAGE_DIR / "profile_README.md"
    path.write_text(text, encoding="utf-8")
    return text, path


# ---------- Agent 4: dispatch ----------

import re
from pathlib import Path

def _find_image(repo, custom_media=None):
    """Dynamically locates screenshots or gameplay media for a repository across CWD and project paths."""
    if custom_media:
        raw_parts = [p.strip() for p in str(custom_media).split(",") if p.strip()]
        valid_parts = [str(Path(p).resolve()) for p in raw_parts if Path(p).exists()]
        if valid_parts:
            return ",".join(valid_parts)

    short_repo = repo.split("/")[-1]
    image_names = [
        f"gameplay_{short_repo}",
        f"{short_repo}",
        "gameplay",
        "gameplay_window",
        "screenshot",
        "preview",
        "demo",
        "thumbnail",
        "cover",
    ]
    exts = [".png", ".jpg", ".jpeg", ".webp", ".gif"]

    search_dirs = [
        Path.cwd(),
        Path.cwd() / "assets",
        Path.cwd() / "images",
        Path.cwd() / "docs",
        config.STORAGE_DIR,
        config.STORAGE_DIR / "drafts",
        Path.home() / "Desktop" / "projects" / "RayLib-Games" / short_repo,
        Path.home() / "Desktop" / "projects" / short_repo,
    ]

    for d in search_dirs:
        if not d.exists():
            continue
        for name in image_names:
            for ext in exts:
                candidate = d / f"{name}{ext}"
                if candidate.exists():
                    return str(candidate.resolve())

    return None

def _fill(text, url):
    return text.replace(drafts.PLACEHOLDER, url)


def _clean_text(text, url):
    """Replaces placeholders and strips any prompt visual cues like (Visual: ...) or [Screenshot: ...]."""
    filled = _fill(text, url)
    cleaned = re.sub(r"\n*[\(\[](?:Visual|Screenshot|Image|GIF|Video):[^)\]]+[\)\]]", "", filled, flags=re.I)
    return cleaned.strip()


def _post_x(d, url, media_path=None):
    repo = url.replace("https://github.com/", "")
    img = media_path or _find_image(repo, getattr(d, "visual_asset", None))
    clean_tweets = [_clean_text(t, url) for t in d.tweets]
    ids = tool_x.post_thread(clean_tweets, media_path=img)
    return ids[0], tool_x.thread_url(ids[0])


def _post_reddit(d, url, media_path=None):
    return tool_reddit.post(d.reddit_subreddit, _clean_text(d.reddit_title, url), _clean_text(d.reddit_body, url))


def _post_linkedin(d, url, media_path=None):
    return tool_linkedin.post(_clean_text(d.linkedin, url))


def _post_discord(d, url, media_path=None):
    repo = url.replace("https://github.com/", "")
    img = media_path or _find_image(repo, getattr(d, "visual_asset", None))
    return tool_discord.post(_clean_text(d.discord_title, url), _clean_text(d.discord_body, url), url, media_path=img)


def _post_github(d, url, media_path=None):
    repo_name = url.replace("https://github.com/", "")
    return tool_github.update_readme(repo_name, _clean_text(d.github_readme_section, url))


def _post_facebook(d, url, media_path=None):
    return tool_facebook.post(_clean_text(d.facebook, url))


PLATFORMS = [
    ("x", tool_x.configured, _post_x),
    ("reddit", tool_reddit.configured, _post_reddit),
    ("linkedin", tool_linkedin.configured, _post_linkedin),
    ("facebook", tool_facebook.configured, _post_facebook),
    ("discord", tool_discord.configured, _post_discord),
    ("github", tool_github.configured, _post_github),
]




def dispatch(draft_id, target_platforms=None, media_path=None):
    """Posts an approved draft. Safe to run again: platforms that worked are skipped.
    target_platforms can be a list or set of platform names (e.g. ['x', 'linkedin']). If None, posts to all configured.
    media_path overrides/supplies explicit image attachment for media-capable platforms.
    """
    row = db.get_draft(draft_id)
    if row is None:
        raise ValueError(f"No draft with id {draft_id}")
    if row["status"] in ("posted", "rejected"):
        raise ValueError(f"Draft {draft_id} is already {row['status']}.")

    d = drafts.Drafts(**row["drafts"])
    url = f"https://github.com/{row['repo']}"
    done = db.posted_platforms(draft_id)
    results = []

    target_set = {p.lower().strip() for p in target_platforms} if target_platforms else None
    repo = row["repo"]
    active_img = media_path or getattr(d, "visual_asset", None) or _find_image(repo)

    for name, is_ready, post_fn in PLATFORMS:
        if target_set is not None and name not in target_set:
            continue
        if name in done:
            results.append({"platform": name, "state": "ok", "detail": "already posted earlier"})
        elif not is_ready():
            results.append({"platform": name, "state": "skipped", "detail": "no keys in .env"})
        elif config.DRY_RUN:
            results.append({"platform": name, "state": "dry", "detail": "would post (DRY_RUN is on)"})
        else:
            try:
                post_id, link = post_fn(d, url, media_path=active_img)
                db.log_post(draft_id, name, True, post_id, link)
                results.append({"platform": name, "state": "ok", "detail": link or post_id})
            except Exception as e:
                db.log_post(draft_id, name, False, detail=str(e))
                results.append({"platform": name, "state": "failed", "detail": str(e)})

    states = [r["state"] for r in results]
    if config.DRY_RUN:
        status = "dry_run"
    elif "failed" in states:
        status = "partial" if "ok" in states else "failed"
    elif "ok" in states:
        status = "posted"
    else:
        status = "approved"
    db.set_status(draft_id, status)
    return results



def format_audit(results):
    label = {"ok": "OK", "failed": "FAILED", "skipped": "skipped", "dry": "dry run"}
    lines = ["Audit:"]
    for r in results:
        lines.append(f"- {r['platform']}: {label[r['state']]} - {r['detail']}")
    return "\n".join(lines)
