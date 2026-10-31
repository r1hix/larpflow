"""Local Git repository inspection for zero-latency, offline, and private repository ingestion."""
from pathlib import Path
import re
import subprocess


def _run_git(args, cwd):
    """Executes a git command in the target directory and returns stdout as a string."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def resolve_repo_path(repo_arg):
    """Resolves a repo argument (e.g. '.', './my-repo', '/path/to', 'repo-name') to an existing local git directory."""
    if not repo_arg:
        return None

    raw = Path(repo_arg).expanduser()
    # 1. Direct path check
    if raw.exists():
        candidate = raw.resolve()
        if (candidate / ".git").exists():
            return candidate

    # 2. Check relative to current working directory
    cwd_candidate = (Path.cwd() / repo_arg).resolve()
    if (cwd_candidate / ".git").exists():
        return cwd_candidate

    # 3. Check sibling directory in parent folder
    parent_candidate = (Path.cwd().parent / repo_arg).resolve()
    if (parent_candidate / ".git").exists():
        return parent_candidate

    return None


def is_local_repo(repo_arg):
    """Returns True if repo_arg resolves to a local git directory."""
    return resolve_repo_path(repo_arg) is not None


def inspect_local_repo(repo_arg, commit_count=10):
    """Extracts repository facts directly from the local Git repo and filesystem with zero network latency."""
    repo_dir = resolve_repo_path(repo_arg)
    if not repo_dir:
        raise ValueError(f"Local repository path '{repo_arg}' not found or not a valid git repository.")

    # 1. Full name & Remote URL
    remote_url = _run_git(["remote", "get-url", "origin"], cwd=repo_dir)
    full_name = repo_dir.name
    repo_url = f"https://github.com/{full_name}"

    if remote_url:
        # e.g., git@github.com:user/repo.git or https://github.com/user/repo.git
        clean_url = re.sub(r"\.git$", "", remote_url)
        match = re.search(r"github\.com[:/]([^/]+/[^/]+)", clean_url)
        if match:
            full_name = match.group(1)
            repo_url = f"https://github.com/{full_name}"
        else:
            repo_url = remote_url

    # 2. README
    readme_text = ""
    for name in ["README.md", "readme.md", "README", "README.rst", "README.txt"]:
        cand = repo_dir / name
        if cand.is_file():
            try:
                readme_text = cand.read_text(encoding="utf-8", errors="replace")[:6000]
                break
            except Exception:
                pass

    # 3. Description
    description = ""
    git_desc_file = repo_dir / ".git" / "description"
    if git_desc_file.is_file():
        desc_val = git_desc_file.read_text(encoding="utf-8", errors="replace").strip()
        if desc_val and not desc_val.startswith("Unnamed repository"):
            description = desc_val

    if not description and readme_text:
        # Extract first non-header, non-empty line of README as description
        for line in readme_text.splitlines():
            line_s = line.strip()
            if line_s and not line_s.startswith("#") and not line_s.startswith("[!") and len(line_s) > 10:
                description = line_s[:160]
                break

    # 4. Files listing (up to 60 top-level files / folders)
    files = []
    ls_out = _run_git(["ls-files"], cwd=repo_dir)
    if ls_out:
        seen_dirs = set()
        for f in ls_out.splitlines():
            parts = f.split("/")
            if len(parts) > 1:
                top_dir = parts[0] + "/"
                if top_dir not in seen_dirs:
                    seen_dirs.add(top_dir)
                    files.append(top_dir)
            else:
                files.append(f)
            if len(files) >= 60:
                break
    else:
        for entry in sorted(repo_dir.iterdir()):
            if entry.name.startswith("."):
                continue
            files.append(entry.name + ("/" if entry.is_dir() else ""))
            if len(files) >= 60:
                break

    # 5. Images detection
    images = []
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    search_dirs = [repo_dir, repo_dir / "assets", repo_dir / "images", repo_dir / "docs"]
    for d in search_dirs:
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in image_exts:
                    images.append({
                        "name": f.name,
                        "path": str(f.resolve()),
                        "url": str(f.resolve()),
                    })

    # Images referenced in README markdown
    if readme_text:
        md_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', readme_text)
        for alt, img_path in md_images:
            resolved_img = (repo_dir / img_path.lstrip("/")).resolve()
            if resolved_img.exists() and not any(i["path"] == str(resolved_img) for i in images):
                images.append({
                    "name": alt or resolved_img.name,
                    "path": str(resolved_img),
                    "url": str(resolved_img),
                })

    # 6. Recent commits & diffs
    commits = []
    log_format = "%h%x09%ad%x09%s"
    count = max(1, min(int(commit_count), 50))
    raw_log = _run_git(["log", f"-n{count}", f"--pretty=format:{log_format}", "--date=short"], cwd=repo_dir)

    if raw_log:
        for idx, line in enumerate(raw_log.splitlines()):
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            sha, date_str, msg = parts[0], parts[1], parts[2]
            entry = {
                "sha": sha,
                "date": date_str,
                "message": msg,
            }
            if idx < 5:  # Diff extracts for up to 5 newest commits
                patch_out = _run_git(["show", "--patch", "--stat", "-n1", sha], cwd=repo_dir)
                if patch_out:
                    entry["changed"] = [
                        {"file": "commit_diff", "patch": patch_out[:2000]}
                    ]
            commits.append(entry)

    # 7. Languages detection from file extensions
    ext_lang_map = {
        ".py": "Python",
        ".c": "C",
        ".h": "C",
        ".cpp": "C++",
        ".cc": "C++",
        ".hpp": "C++",
        ".rs": "Rust",
        ".go": "Go",
        ".swift": "Swift",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".jsx": "React",
        ".tsx": "React",
        ".sh": "Shell",
        ".java": "Java",
        ".rb": "Ruby",
        ".html": "HTML",
        ".css": "CSS",
    }
    languages = {}
    if ls_out:
        for f in ls_out.splitlines():
            ext = Path(f).suffix.lower()
            if ext in ext_lang_map:
                lang = ext_lang_map[ext]
                languages[lang] = languages.get(lang, 0) + 1

    last_commit_date = commits[0]["date"] if commits else ""

    return {
        "full_name": full_name,
        "url": repo_url,
        "description": description,
        "languages": languages,
        "topics": [],
        "stars": 0,
        "last_push": last_commit_date,
        "readme": readme_text,
        "files": files,
        "images": images,
        "recent_commits": commits,
        "closed_issues": [],
        "local_path": str(repo_dir),
    }

