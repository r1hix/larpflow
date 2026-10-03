"""The flow: ingest -> draft -> (human approves) -> dispatch. Used by the bot and the CLI."""
from . import config, db, drafts
from tools import tool_discord, tool_github, tool_linkedin, tool_reddit, tool_x


def parse_run_args(text):
    parts = [p.strip() for p in text.split("|", 2)]
    if len(parts) == 1 and parts[0]:
        return parts[0], "", ""
    if len(parts) != 3 or not all(parts):
        raise ValueError("Use it like this:\nlarpflow run repo-name\nor: larpflow run 'repo-name | problem | solution'")
    return parts


def make_drafts(repo, problem="", solution=""):
    """Agent 1 + Agent 2. Returns (draft_id, repo_info, drafts)."""
    info = tool_github.inspect_repo(repo)
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

    d = drafts.generate(info, problem, solution, past)
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

def _fill(text, url):
    return text.replace(drafts.PLACEHOLDER, url)


def _post_x(d, url):
    ids = tool_x.post_thread([_fill(t, url) for t in d.tweets])
    return ids[0], tool_x.thread_url(ids[0])


def _post_reddit(d, url):
    return tool_reddit.post(d.reddit_subreddit, d.reddit_title, d.reddit_body)


def _post_linkedin(d, url):
    return tool_linkedin.post(_fill(d.linkedin, url))


def _post_discord(d, url):
    return tool_discord.post(d.discord_title, d.discord_body, url)


def _post_github(d, url):
    repo_name = url.replace("https://github.com/", "")
    return tool_github.update_readme(repo_name, d.github_readme_section)


PLATFORMS = [
    ("x", tool_x.configured, _post_x),
    ("reddit", tool_reddit.configured, _post_reddit),
    ("linkedin", tool_linkedin.configured, _post_linkedin),
    ("discord", tool_discord.configured, _post_discord),
    ("github", tool_github.configured, _post_github),
]



def dispatch(draft_id, target_platforms=None):
    """Posts an approved draft. Safe to run again: platforms that worked are skipped.
    target_platforms can be a list or set of platform names (e.g. ['x', 'linkedin']). If None, posts to all configured.
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
                post_id, link = post_fn(d, url)
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
