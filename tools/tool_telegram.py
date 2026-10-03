"""Agent 3 (the gatekeeper): shows drafts in Telegram with buttons."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core import drafts as draft_lib


def keyboard(draft_id):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 Post All", callback_data=f"approve:{draft_id}:all"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{draft_id}:all"),
            ],
            [
                InlineKeyboardButton("Post X", callback_data=f"approve:{draft_id}:x"),
                InlineKeyboardButton("Post LinkedIn", callback_data=f"approve:{draft_id}:linkedin"),
            ],
            [
                InlineKeyboardButton("Post Reddit", callback_data=f"approve:{draft_id}:reddit"),
                InlineKeyboardButton("Post Discord", callback_data=f"approve:{draft_id}:discord"),
            ],
            [
                InlineKeyboardButton("✏️ Edit X", callback_data=f"edit:{draft_id}:x"),
                InlineKeyboardButton("✏️ Edit LinkedIn", callback_data=f"edit:{draft_id}:linkedin"),
            ],
        ]
    )



def split_text(text, limit=3800):
    """Telegram allows 4096 chars per message, so cut on line breaks."""
    chunks, current = [], ""
    for line in text.splitlines():
        while len(line) > limit:  # one crazy long line
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks or [""]


async def send_approval_bundle(message, draft_id, repo, d):
    """message is any Telegram message we can reply to. Buttons go on the last chunk."""
    chunks = split_text(draft_lib.render_preview(draft_id, repo, d))
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        await message.reply_text(chunk, reply_markup=keyboard(draft_id) if is_last else None)
