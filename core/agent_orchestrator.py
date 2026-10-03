"""The Telegram bot. Run it with: python -m core.agent_orchestrator"""
import asyncio
import functools
import io
import logging
import re

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import config, db, drafts, pipeline
from tools import tool_github, tool_telegram

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("larpflow")

HELP = """LarpFlow commands:
/run repo | problem | solution  - make drafts
/repos  - list your GitHub repos
/history  - what was drafted and posted
/readme  - make a new GitHub profile README
/whoami  - show your Telegram id (for .env)"""


def owner_only(fn):
    """Only the owner can use the bot. Everyone else gets ignored."""

    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != config.TELEGRAM_OWNER_ID:
            return
        return await fn(update, context)

    return wrapper


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram id is {update.effective_user.id}")


@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)


@owner_only
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.partition(" ")[2]
    try:
        repo, problem, solution = pipeline.parse_run_args(text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    await update.message.reply_text(f"Reading {repo} and writing drafts. Give me a minute...")
    try:
        draft_id, info, d = await asyncio.to_thread(pipeline.make_drafts, repo, problem, solution)
    except Exception as e:
        log.exception("make_drafts failed")
        await update.message.reply_text(f"That failed: {e}")
        return
    await tool_telegram.send_approval_bundle(update.message, draft_id, info["full_name"], d)


@owner_only
async def cmd_repos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        repos = await asyncio.to_thread(tool_github.list_repos)
    except Exception as e:
        await update.message.reply_text(f"That failed: {e}")
        return
    lines = [f"{r['name']} ({r['language'] or '?'}) - {r['description'] or 'no description'}" for r in repos]
    for chunk in tool_telegram.split_text("\n".join(lines) or "No repos found."):
        await update.message.reply_text(chunk)


@owner_only
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.recent_history(10)
    lines = [f"#{r['id']} {r['repo']} [{r['status']}] -> {r['platforms'] or '-'}" for r in rows]
    await update.message.reply_text("\n".join(lines) or "No history yet.")


@owner_only
async def cmd_readme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Writing a profile README from your repos...")
    try:
        text, _path = await asyncio.to_thread(pipeline.make_profile_readme)
    except Exception as e:
        log.exception("readme failed")
        await update.message.reply_text(f"That failed: {e}")
        return
    await update.message.reply_document(document=io.BytesIO(text.encode("utf-8")), filename="README.md")


@owner_only
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    action = parts[0]
    draft_id = int(parts[1])
    target = parts[2] if len(parts) > 2 else "all"

    row = db.get_draft(draft_id)
    if row is None:
        await query.message.reply_text(f"Draft #{draft_id} not found.")
        return

    if action == "approve":
        mode = " (DRY RUN, nothing really posts)" if config.DRY_RUN else ""
        target_platforms = None if target == "all" else [target]
        target_desc = "all platforms" if target == "all" else target.upper()
        await query.message.reply_text(f"Publishing #{draft_id} to {target_desc}{mode}...")
        try:
            results = await asyncio.to_thread(pipeline.dispatch, draft_id, target_platforms)
        except Exception as e:
            log.exception("dispatch failed")
            await query.message.reply_text(f"That failed: {e}")
            return
        await query.message.reply_text(pipeline.format_audit(results))

    elif action == "edit":
        context.user_data["editing_draft_id"] = draft_id
        context.user_data["editing_platform"] = target
        if target == "linkedin":
            await query.message.reply_text(
                "Send the new LinkedIn post as a single message (150-250 words, max 3 hashtags). Send /cancel to stop."
            )
        else:
            await query.message.reply_text(
                "Send the new tweets as ONE message. Put a line with just --- between tweets. "
                "I need exactly 4. Send /cancel to stop."
            )

    elif action == "reject":
        db.set_status(draft_id, "rejected")
        context.user_data.pop("editing_draft_id", None)
        context.user_data.pop("editing_platform", None)
        await query.message.reply_text(f"Draft #{draft_id} rejected. Nothing was posted.")


@owner_only
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("editing_draft_id", None)
    context.user_data.pop("editing_platform", None)
    await update.message.reply_text("Okay, cancelled.")


@owner_only
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft_id = context.user_data.get("editing_draft_id")
    platform = context.user_data.get("editing_platform", "x")
    if not draft_id:
        return

    row = db.get_draft(draft_id)
    if not row:
        context.user_data.pop("editing_draft_id", None)
        context.user_data.pop("editing_platform", None)
        return

    d = drafts.Drafts(**row["drafts"])

    if platform == "linkedin":
        text = update.message.text.strip()
        words = len(text.split())
        hashtags = len(re.findall(r"#\w+", text))
        issues = []
        if not 150 <= words <= 250:
            issues.append(f"linkedin post is {words} words (need 150 to 250)")
        if hashtags > 3:
            issues.append("linkedin has more than 3 hashtags")
        if issues:
            await update.message.reply_text("Not saved:\n- " + "\n- ".join(issues) + "\nTry again or send /cancel.")
            return
        d.linkedin = text
    else:
        tweets = [t.strip() for t in re.split(r"\n\s*---\s*\n", update.message.text.strip())]
        issues = drafts.tweet_problems(tweets)
        if issues:
            await update.message.reply_text("Not saved:\n- " + "\n- ".join(issues) + "\nTry again or send /cancel.")
            return
        d.tweets = tweets

    db.update_drafts(draft_id, d.model_dump())
    context.user_data.pop("editing_draft_id", None)
    context.user_data.pop("editing_platform", None)
    await update.message.reply_text("Updated draft:")
    await tool_telegram.send_approval_bundle(update.message, draft_id, row["repo"], d)



def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is empty. Fill in .env first (or use: python -m core.cli).")
    if not config.TELEGRAM_OWNER_ID:
        print("Heads up: TELEGRAM_OWNER_ID is empty, so the bot ignores everyone.")
        print("Send /whoami to the bot, copy the number into .env, then restart.")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("repos", cmd_repos))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("readme", cmd_readme))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    mode = "DRY RUN (nothing posts)" if config.DRY_RUN else "LIVE"
    log.info("LarpFlow bot is running in %s mode", mode)
    app.run_polling()


if __name__ == "__main__":
    main()
