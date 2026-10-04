"""Terminal version of LarpFlow. Handy for testing without Telegram.

python -m core.cli doctor
python -m core.cli run "repo | problem | solution"
python -m core.cli send 3
python -m core.cli history
python -m core.cli readme
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path even when executed outside the repo root
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import config, db, drafts, pipeline
from tools import tool_discord, tool_facebook, tool_github, tool_linkedin, tool_reddit, tool_x


def cmd_doctor(_args):
    def mark(ok):
        return "ok     " if ok else "MISSING"

    print(f"DRY_RUN            : {'ON (nothing will post)' if config.DRY_RUN else 'OFF (posts for real!)'}")
    print(f"LLM key            : {mark(config.LLM_API_KEY)}  model={config.LLM_MODEL}")
    print(f"GitHub token       : {mark(config.GITHUB_TOKEN)}  (optional for public repos)")
    print(f"Telegram token     : {mark(config.TELEGRAM_BOT_TOKEN)}")
    print(f"Telegram owner id  : {mark(config.TELEGRAM_OWNER_ID)}")
    print(f"X                  : {mark(tool_x.configured())}")
    print(f"Reddit             : {mark(tool_reddit.configured())}  subs={config.REDDIT_ALLOWED_SUBS}")
    print(f"LinkedIn           : {mark(tool_linkedin.configured())}")
    print(f"Facebook           : {mark(tool_facebook.configured())}")
    print(f"Discord            : {mark(tool_discord.configured())}")
    print(f"LinkedIn profile   : {mark(config.load_linkedin_profile())}  (config/linkedin_profile.md)")



def cmd_run(args):
    # Support either positional string "repo | prob | sol" or explicit CLI flags
    raw_repo, raw_prob, raw_sol = pipeline.parse_run_args(args.text)
    repo = raw_repo
    problem = args.problem or raw_prob
    solution = args.solution or raw_sol
    media = args.image or ""

    print(f"Working... (inspecting GitHub '{repo}' with {args.commits} commits, type='{args.type}')...")
    draft_id, info, d = pipeline.make_drafts(
        repo,
        problem=problem,
        solution=solution,
        commit_count=args.commits,
        post_type=args.type,
        media_path=media,
    )
    preview_text = drafts.render_preview(draft_id, info["full_name"], d)
    print(preview_text)

    # Auto-export draft as an editable Markdown file and open it in the editor
    draft_dir = config.STORAGE_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_file = draft_dir / f"draft_{draft_id}_{repo.replace('/', '_')}.md"
    draft_file.write_text(preview_text, encoding="utf-8")
    print(f"\nSaved draft to {draft_file}")

    try:
        import subprocess
        subprocess.run(["open", str(draft_file)], check=False)
        print(f"Opened {draft_file.name} in your editor.")
    except Exception:
        pass

    print(f"\nTo post it: larpflow send {draft_id} --yes (or: python -m core.cli send {draft_id})")




def cmd_show(args):
    row = db.get_draft(args.draft_id)
    if row is None:
        raise SystemExit(f"No draft #{args.draft_id}")
    d = drafts.Drafts(**row["drafts"])
    print(drafts.render_preview(args.draft_id, row["repo"], d))


def cmd_repos(_args):
    repos = tool_github.list_repos()
    for r in repos:
        print(f"{r['name']} ({r['language'] or '?'}) - {r['description'] or 'no description'} [{r['url']}]")


def cmd_send(args):
    row = db.get_draft(args.draft_id)
    if row is None:
        raise SystemExit(f"No draft #{args.draft_id}")
    mode = "DRY RUN" if config.DRY_RUN else "LIVE (posts for real)"
    platforms = [p.strip() for p in args.platforms.split(",")] if args.platforms else None
    target_str = f"to {args.platforms}" if args.platforms else "to all platforms"
    media = args.image or ""
    
    if not args.yes:
        answer = input(f"Send draft #{args.draft_id} for {row['repo']} {target_str} in {mode} mode? Type yes: ")
        if answer.strip().lower() != "yes":
            raise SystemExit("Cancelled.")
    else:
        print(f"Sending draft #{args.draft_id} {target_str} in {mode} mode...")

    print(pipeline.format_audit(pipeline.dispatch(args.draft_id, target_platforms=platforms, media_path=media)))


def cmd_history(_args):
    rows = db.recent_history(15)
    if not rows:
        print("No history yet.")
    for r in rows:
        print(f"#{r['id']} {r['created_at']} {r['repo']} [{r['status']}] posted to: {r['platforms'] or '-'}")


def cmd_readme(_args):
    text, path = pipeline.make_profile_readme()
    print(text)
    print(f"\nSaved to {path}")


def main():
    parser = argparse.ArgumentParser(prog="larpflow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="show which keys are filled in").set_defaults(fn=cmd_doctor)
    sub.add_parser("repos", help="list your GitHub repos").set_defaults(fn=cmd_repos)
    
    run = sub.add_parser("run", help="make drafts for a repo")
    run.add_argument("text", help='repo name or "repo | problem | solution"')
    run.add_argument("--commits", "-c", type=int, default=10, help="number of recent commits to inspect (default 10)")
    run.add_argument(
        "--type",
        "-t",
        choices=["auto", "intro", "motivation", "bug", "architecture", "full_project", "tech_stack", "showcase"],
        default="auto",
        help="narrative focus of the post",
    )
    run.add_argument("--problem", help="custom motivation, problem, or bottleneck context", default="")
    run.add_argument("--solution", help="custom fix, architectural solution, or takeaways", default="")
    run.add_argument("--image", "-i", default="", help="custom image path for media attachments (e.g. screenshot or gameplay)")
    run.set_defaults(fn=cmd_run)


    
    show = sub.add_parser("show", help="preview an existing draft by id")
    show.add_argument("draft_id", type=int)
    show.set_defaults(fn=cmd_show)

    send = sub.add_parser("send", help="post a saved draft")
    send.add_argument("draft_id", type=int)
    send.add_argument("--platforms", "-p", help="comma-separated list: x,linkedin,facebook,reddit,discord,github", default="")
    send.add_argument("--image", "-i", default="", help="custom image path for media attachments (overrides auto-detection)")
    send.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt")
    send.set_defaults(fn=cmd_send)

    
    sub.add_parser("history", help="show past drafts").set_defaults(fn=cmd_history)
    sub.add_parser("readme", help="make a new GitHub profile README").set_defaults(fn=cmd_readme)
    args = parser.parse_args()
    args.fn(args)





if __name__ == "__main__":
    main()
