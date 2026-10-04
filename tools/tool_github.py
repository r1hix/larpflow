"""Agent 1 (the ingestor): reads repos from GitHub."""
from github import Auth, Github, GithubException

from core import config


def _gh():
    if config.GITHUB_TOKEN:
        return Github(auth=Auth.Token(config.GITHUB_TOKEN))
    return Github()  # works for public repos, but rate limited


def _full_name(name):
    name = name.strip().replace("https://github.com/", "").strip("/")
    if name.endswith(".git"):
        name = name[:-4]
    return name if "/" in name else f"{config.GITHUB_USER}/{name}"


def list_repos(limit=40):
    """Your own (non-fork) repos, newest push first."""
    out = []
    for repo in _gh().get_user(config.GITHUB_USER).get_repos(type="owner", sort="pushed"):
        if repo.fork:
            continue
        out.append(
            {
                "name": repo.name,
                "description": repo.description,
                "language": repo.language,
                "stars": repo.stargazers_count,
                "url": repo.html_url,
                "last_push": repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "",
            }
        )
        if len(out) >= limit:
            break
    return out


def inspect_repo(name, commit_count=10):
    """Collects the facts the stylist is allowed to use."""
    full = _full_name(name)
    gh = _gh()
    try:
        repo = gh.get_repo(full)
    except GithubException as e:
        if e.status == 404:
            raise ValueError(f"Repo {full} not found. (Private repos need GITHUB_TOKEN in .env)")
        raise

    readme = ""
    try:
        readme = repo.get_readme().decoded_content.decode("utf-8", "replace")[:6000]
    except GithubException:
        pass

    files = []
    images = []
    try:
        for c in repo.get_contents("")[:60]:
            path_str = c.path + ("/" if c.type == "dir" else "")
            files.append(path_str)
            if c.type != "dir":
                ext = c.name.lower().split(".")[-1]
                if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
                    images.append({"name": c.name, "path": c.path, "url": c.download_url or f"https://raw.githubusercontent.com/{full}/HEAD/{c.path}"})
    except GithubException:
        pass

    # Also detect images linked in README markdown
    import re
    md_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', readme)
    for alt, img_path in md_images:
        if not any(i["path"] == img_path for i in images):
            images.append({"name": alt or img_path.split("/")[-1], "path": img_path, "url": img_path if img_path.startswith("http") else f"https://raw.githubusercontent.com/{full}/HEAD/{img_path.lstrip('/')}"})

    commits = []
    try:
        count = max(1, min(int(commit_count), 50))
        for i, c in enumerate(repo.get_commits()[:count]):
            entry = {
                "sha": c.sha[:7],
                "date": c.commit.author.date.strftime("%Y-%m-%d"),
                "message": c.commit.message.splitlines()[0],
            }
            if i < 5:  # diffs for up to 5 newest commits
                try:
                    entry["changed"] = [
                        {"file": f.filename, "patch": (f.patch or "")[:800]} for f in list(c.files)[:5]
                    ]
                except GithubException:
                    pass
            commits.append(entry)
    except GithubException:
        pass  # empty repo

    issues = []
    try:
        for issue in repo.get_issues(state="closed")[:15]:
            if issue.pull_request is None:
                issues.append({"title": issue.title, "body": (issue.body or "")[:400]})
            if len(issues) >= 5:
                break
    except GithubException:
        pass

    try:
        languages = repo.get_languages()
    except GithubException:
        languages = {}

    return {
        "full_name": repo.full_name,
        "url": repo.html_url,
        "description": repo.description,
        "languages": languages,
        "topics": repo.get_topics(),
        "stars": repo.stargazers_count,
        "last_push": repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "",
        "readme": readme,
        "files": files,
        "images": images,
        "recent_commits": commits,
        "closed_issues": issues,
    }


def configured():
    return bool(config.GITHUB_TOKEN)


def update_readme(repo_name, new_section):
    """Commits and pushes the generated section into the repo's README.md."""
    full = _full_name(repo_name)
    gh = _gh()
    repo = gh.get_repo(full)

    target_content = f"\n\n## Architecture & Technical Trade-offs\n\n{new_section.strip()}\n"

    try:
        current_file = repo.get_readme()
        existing = current_file.decoded_content.decode("utf-8", "replace")
        marker = "## Architecture & Technical Trade-offs"
        if marker in existing:
            # Replace existing section
            pre = existing.split(marker)[0].rstrip()
            updated = f"{pre}\n\n{marker}\n\n{new_section.strip()}\n"
        else:
            updated = f"{existing.rstrip()}\n{target_content}"

        commit = repo.update_file(
            path=current_file.path,
            message="docs: update architecture & technical trade-offs via LarpFlow",
            content=updated,
            sha=current_file.sha,
        )
        return commit["commit"].sha[:7], repo.html_url
    except GithubException:
        # If no README exists yet, create one
        commit = repo.create_file(
            path="README.md",
            message="docs: initialize README with architecture section via LarpFlow",
            content=target_content.strip(),
        )
        return commit["commit"].sha[:7], repo.html_url

