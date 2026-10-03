"""Terminal version of LarpFlow. Handy for testing without Telegram.

python -m core.cli doctor
python -m core.cli run "repo | problem | solution"
python -m core.cli send 3
python -m core.cli history
python -m core.cli readme
"""
import argparse

from . import config, db, drafts, pipeline
from tools import tool_discord, tool_github, tool_linkedin, tool_reddit, tool_x



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
    print(f"Discord            : {mark(tool_discord.configured())}")
    print(f"LinkedIn profile   : {mark(config.load_linkedin_profile())}  (config/linkedin_profile.md)")


def cmd_run(args):
    repo, problem, solution = pipeline.parse_run_args(args.text)
    print("Working... (reads GitHub, then asks the model)")
    draft_id, info, d = pipeline.make_drafts(repo, problem, solution)
    print(drafts.render_preview(draft_id, info["full_name"], d))
    print(f"Saved as draft #{draft_id}. To post it: python -m core.cli send {draft_id}")


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
    
    if not args.yes:
        answer = input(f"Send draft #{args.draft_id} for {row['repo']} {target_str} in {mode} mode? Type yes: ")
        if answer.strip().lower() != "yes":
            raise SystemExit("Cancelled.")
    else:
        print(f"Sending draft #{args.draft_id} {target_str} in {mode} mode...")

    print(pipeline.format_audit(pipeline.dispatch(args.draft_id, target_platforms=platforms)))


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
    run.set_defaults(fn=cmd_run)
    send = sub.add_parser("send", help="post a saved draft")
    send.add_argument("draft_id", type=int)
    send.add_argument("--platforms", "-p", help="comma-separated list: x,linkedin,reddit,discord", default="")
    send.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt")
    send.set_defaults(fn=cmd_send)
    sub.add_parser("history", help="show past drafts").set_defaults(fn=cmd_history)
    sub.add_parser("readme", help="make a new GitHub profile README").set_defaults(fn=cmd_readme)
    args = parser.parse_args()
    args.fn(args)




if __name__ == "__main__":
    main()
