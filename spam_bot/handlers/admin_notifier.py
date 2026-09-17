import asyncio
import logging
import time
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, ChatPermissions,
    InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from ..core import copy, groups, patterns, stats, usage, watchlist
from ..core.config import ADMIN_TELEGRAM_IDS, MAX_GROUPS_PER_OWNER, OPERATOR_ALERTS
from ..core.ratelimit import RateLimiter

router = Router()

# Keep groups tidy: transient bot notices (mute/ban announcements, command acks)
# and the admin command messages themselves are removed shortly after they serve
# their purpose, instead of piling up in the chat.
_SERVICE_TTL = 5.0  # seconds a transient in-group bot message stays visible


async def _delete_after(bot, chat_id: int, message_id: int, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def autodelete(bot, chat_id: int, message_id: int, delay: float = _SERVICE_TTL) -> None:
    """Fire-and-forget delete of a transient in-group bot message after `delay`s."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop (e.g. unit test) — nothing to schedule
    asyncio.create_task(_delete_after(bot, chat_id, message_id, delay))


async def delete_command(message) -> None:
    """Best-effort immediate delete of an incoming command message (group only —
    bots can't delete other users' messages in private chats)."""
    try:
        await message.bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass


async def reply_temp(message, text, **kwargs):
    """Reply, then auto-delete the reply after _SERVICE_TTL in group chats (in DMs
    the reply stays). Returns the sent message, or None on failure."""
    try:
        sent = await message.reply(text, **kwargs)
    except Exception:
        return None
    if message.chat.type in ("group", "supergroup"):
        autodelete(message.bot, sent.chat.id, sent.message_id)
    return sent


def _is_admin(user_id: int) -> bool:
    return str(user_id) in ADMIN_TELEGRAM_IDS


async def send_to_admins(bot, text: str, reply_markup=None) -> None:
    """Fan a message out to every configured admin."""
    if not ADMIN_TELEGRAM_IDS:
        logging.warning("No admin Telegram IDs configured — skipping notification")
        return
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, reply_markup=reply_markup)
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")


_group_admin_cache: dict = {}   # chat_id -> (set[int], monotonic_ts)
_GROUP_ADMIN_TTL = 300.0


async def _group_admin_ids(bot, chat_id: int) -> set:
    """Live admin user-ids for a chat (cached ~5 min), bots excluded."""
    cached = _group_admin_cache.get(chat_id)
    if cached is None or time.monotonic() - cached[1] > _GROUP_ADMIN_TTL:
        try:
            admins = await bot.get_chat_administrators(chat_id)
            ids = {a.user.id for a in admins if not a.user.is_bot}
            _group_admin_cache[chat_id] = (ids, time.monotonic())
            return ids
        except Exception as e:
            logging.error(f"get_chat_administrators failed for {chat_id}: {e}")
            return cached[0] if cached else set()
    return cached[0]


async def _can_moderate(bot, chat_id: int, user_id: int) -> bool:
    """Operator (env) or an admin of this chat may act on its alerts."""
    return _is_admin(user_id) or user_id in await _group_admin_ids(bot, chat_id)


async def _bot_can_moderate(bot, chat_id: int) -> bool:
    """True if the bot itself is an admin able to delete messages and ban users —
    without these rights moderation silently no-ops, so /enable must check."""
    try:
        me = await bot.get_me()
        m = await bot.get_chat_member(chat_id, me.id)
        return m.status == "administrator" and getattr(m, "can_delete_messages", False) \
            and getattr(m, "can_restrict_members", False)
    except Exception as e:
        logging.error(f"_bot_can_moderate failed for {chat_id}: {e}")
        return False


async def notify_group(bot, chat_id: int, text: str, reply_markup=None) -> None:
    """DM a group's own admins (enabled_by + live admins). If nobody is reachable
    (no admin has started the bot), the alert is logged and dropped — we do NOT
    fall back to the operator. Otherwise every keyless stranger group turns the
    operator into its alert dump. The in-group onboarding hint tells admins to
    start the bot; until one does, the group simply gets no DM alerts."""
    recipients = set(await _group_admin_ids(bot, chat_id))
    eb = groups.enabled_by(chat_id)
    if eb:
        recipients.add(eb)
    sent = 0
    for uid in recipients:
        try:
            await bot.send_message(chat_id=uid, text=text, reply_markup=reply_markup)
            sent += 1
        except Exception as e:
            logging.info(f"alert not delivered to {uid}: {e}")
    if sent == 0:
        logging.info(f"alert dropped: no reachable admin for chat {chat_id}")


_chat_title_cache: dict = {}    # chat_id -> (title, monotonic_ts)
_CHAT_TITLE_TTL = 900.0         # renames are rare; a stale name for 15 min is fine


async def _chat_title(bot, chat_id: int) -> str:
    """Group title for operator alerts, cached. Falls back to the raw id — the
    alert must still say *which* group even when get_chat fails."""
    cached = _chat_title_cache.get(chat_id)
    if cached and time.monotonic() - cached[1] <= _CHAT_TITLE_TTL:
        return cached[0]
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
    except Exception as e:
        logging.info(f"get_chat failed for {chat_id}: {e}")
        return cached[0] if cached else str(chat_id)
    _chat_title_cache[chat_id] = (title, time.monotonic())
    return title


async def _user_label(bot, chat_id: int, user_id: int) -> str:
    """'Name (@handle)' for a user id. Best-effort: a banned account may already
    be gone, in which case the id alone still identifies them."""
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        u = m.user
        return f"{u.full_name} (@{u.username})" if u.username else u.full_name
    except Exception:
        return "?"


async def notify_operator_action(bot, chat_id: int, user_id: int, action: str,
                                 reason: str, user_type: str = "",
                                 by: str = "") -> None:
    """Mirror one moderation action to the operator DMs, naming the group and the
    account. No-op unless OPERATOR_ALERTS is set — see config.py for why the
    default keeps group alerts inside the group."""
    if not OPERATOR_ALERTS or not ADMIN_TELEGRAM_IDS:
        return
    try:
        title = await _chat_title(bot, chat_id)
        who = await _user_label(bot, chat_id, user_id)
        lines = [
            f"{action}",
            f"💬 Guruh: {title} ({chat_id})",
            f"👤 Foydalanuvchi: {who}",
            f"🆔 {user_id}",
        ]
        if user_type:
            lines.append(f"👥 Turi: {user_type}")
        if by:
            lines.append(f"🧑‍⚖️ Kim: {by}")
        lines.append(f"📝 Sabab: {reason}")
        lines.append(f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")
        await send_to_admins(bot, "\n".join(lines))
    except Exception as e:
        # An operator alert must never break the moderation action that triggered it.
        logging.error(f"notify_operator_action failed for {user_id}@{chat_id}: {e}")


def action_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Ban / Unmute buttons for an admin alert about `user_id` in `chat_id`."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔨 Ban", callback_data=f"act:ban:{chat_id}:{user_id}"),
        InlineKeyboardButton(text="✅ Unmute", callback_data=f"act:unmute:{chat_id}:{user_id}"),
    ]])


_ALL_PERMS = ChatPermissions(
    can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
    can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True,
)
_MUTED = ChatPermissions(
    can_send_messages=False, can_send_media_messages=False, can_send_polls=False,
    can_send_other_messages=False, can_add_web_page_previews=False,
)


async def _is_group_admin(message: Message) -> bool:
    """True if the sender is an admin of this group (or the bot owner). Handles
    anonymous admins, who post as the group itself."""
    if message.from_user and _is_admin(message.from_user.id):
        return True
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True  # anonymous group admin
    if not message.from_user:
        return False
    try:
        m = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in ("creator", "administrator")
    except Exception as e:
        logging.error(f"get_chat_member failed: {e}")
        return False


@router.callback_query(F.data.startswith("act:"))
async def on_admin_action(cb: CallbackQuery) -> None:
    _, action, chat_id, user_id = cb.data.split(":")
    chat_id, user_id = int(chat_id), int(user_id)
    if not await _can_moderate(cb.bot, chat_id, cb.from_user.id):
        await cb.answer("Not authorized.")
        return
    try:
        if action == "ban":
            await cb.bot.ban_chat_member(chat_id, user_id)
            note = f"\n\n🔨 Banned by @{cb.from_user.username or cb.from_user.id}."
            await notify_operator_action(
                cb.bot, chat_id, user_id, "🔨 BAN (admin tugma orqali)",
                "admin alert'dagi Ban tugmasi",
                by=f"@{cb.from_user.username or cb.from_user.id}")
        else:  # unmute
            await cb.bot.restrict_chat_member(chat_id, user_id, permissions=_ALL_PERMS)
            note = f"\n\n✅ Unmuted by @{cb.from_user.username or cb.from_user.id}."
        if cb.message:
            await cb.message.edit_text((cb.message.text or "") + note)
        await cb.answer("Done")
    except Exception as e:
        await cb.answer(f"Failed: {e}", show_alert=True)


async def notify_admins(bot, message: Message, reason: str, user_type: str) -> None:
    text = message.text or message.caption or "No text"
    if len(text) > 200:
        text = text[:200] + "..."
    await notify_group(bot, message.chat.id, (
        f"🚨 SPAM DETECTED 🚨\n\n"
        f"👥 User: {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"🆔 User ID: {message.from_user.id}\n"
        f"💬 Group: {message.chat.title or message.chat.id}\n"
        f"📝 Reason: {reason}\n"
        f"👤 Type: {user_type}\n"
        f"📄 Message: {text}\n"
        f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        f"⚠️ Action taken: User blocked"
    ), reply_markup=action_keyboard(message.chat.id, message.from_user.id))


async def notify_admins_burst(bot, message: Message, reason: str, actioned: list,
                              banned: bool = False) -> None:
    """One alert for a coordinated link flood instead of one per account. Every
    copy is already deleted. Muted senders get an Unmute button each; banned ones
    (a VirusTotal-confirmed link) are listed without one."""
    text = message.text or message.caption or "No text"
    if len(text) > 200:
        text = text[:200] + "..."
    rows = [] if banned else [
        [InlineKeyboardButton(text=f"✅ Unmute: {_short(name or str(uid))}",
                              callback_data=f"act:unmute:{message.chat.id}:{uid}")]
        for uid, name in actioned[:10]]
    action = "senders banned" if banned else "senders muted for 24h"
    await notify_group(bot, message.chat.id, (
        f"🚨 LINK FLOOD 🚨\n\n"
        f"💬 Group: {message.chat.title or message.chat.id}\n"
        f"📊 {len(actioned)} accounts sent the same message — every copy deleted, {action}.\n"
        f"📝 Reason: {reason}\n"
        f"📄 Message: {text}\n"
        f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}"
    ), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)


# --- Admin teaching flow: forward spam -> pick keywords -> learn ---------------
# ponytail: in-memory, single-process. Pending proposals are lost on restart;
# approved patterns persist in the DB. Add Redis only if you run multiple workers.
_pending: dict = {}  # (admin_id, proposal_msg_id) -> {"cands", "sel", "cat"}


def _keyboard(state: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅' if i in state['sel'] else '⬜'} {c}",
            callback_data=f"lp:t:{i}",
        )]
        for i, c in enumerate(state["cands"])
    ]
    rows.append([
        InlineKeyboardButton(
            text=("● " if state["cat"] == cat else "") + cat,
            callback_data=f"lp:c:{cat}",
        ) for cat in ("ads", "inappropriate")
    ])
    rows.append([
        InlineKeyboardButton(text="✅ Add selected", callback_data="lp:save"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="lp:x"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Misclassification feedback: forward a message -> tag what's wrong ---------
# ponytail: in-memory, single-process — pending prompts are lost on restart, but
# the report itself is persisted the moment a button is tapped.
_fb_pending: dict = {}   # (admin_id, bot_msg_id) -> {"text", "verdict", "cands"}
_awaiting_note: dict = {}  # (admin_id, bot_msg_id) -> feedback_report_id


def _fb_keyboard(is_spam: bool) -> InlineKeyboardMarkup:
    """Lead with the report that matches the verdict (FP if it flagged, FN if not).
    'Flag account' targets the sender's profile, not the message — for bot accounts
    that post benign text but whose profile pushes spam/explicit content."""
    # Plain-language labels — "false positive/negative" confused admins about which
    # is which. Callback data (fb:fp / fb:fn) is unchanged.
    fp = InlineKeyboardButton(text="🚩 Not spam (wrongly flagged)", callback_data="fb:fp")
    fn = InlineKeyboardButton(text="🐛 This IS spam (you missed it)", callback_data="fb:fn")
    return InlineKeyboardMarkup(inline_keyboard=[
        [fp, fn] if is_spam else [fn, fp],
        [InlineKeyboardButton(text="🕵️ Flag account", callback_data="fb:acct"),
         InlineKeyboardButton(text="📚 Teach keywords", callback_data="fb:teach")],
        [InlineKeyboardButton(text="❌ Close", callback_data="fb:x")],
    ])


def _forward_sender(message: Message) -> tuple[int | None, str | None]:
    """Original sender of a forwarded message: (user_id, display_name).
    Returns (None, name) when the sender is a hidden user (forward privacy),
    and (None, None) when the message wasn't forwarded at all."""
    o = getattr(message, "forward_origin", None)
    if o is not None:
        su = getattr(o, "sender_user", None)
        if su is not None:
            return su.id, su.full_name
        name = getattr(o, "sender_user_name", None)
        if name:
            return None, name
        chat = getattr(o, "sender_chat", None) or getattr(o, "chat", None)
        if chat is not None:
            return chat.id, chat.title or getattr(chat, "full_name", None)
    # Legacy fields (older Bot API payloads).
    if getattr(message, "forward_from", None):
        return message.forward_from.id, message.forward_from.full_name
    if getattr(message, "forward_sender_name", None):
        return None, message.forward_sender_name
    return None, None


def _save_feedback(admin_id: int, text: str, verdict: str, label: str,
                   target_id: int | None = None, target_name: str | None = None,
                   group_id=None) -> int:
    from ..db.session import SessionLocal
    from ..db.models import FeedbackReport
    with SessionLocal() as db:
        fr = FeedbackReport(admin_id=admin_id, message_text=text,
                            bot_verdict=verdict, label=label,
                            target_user_id=target_id, target_name=target_name,
                            group_id=group_id)
        db.add(fr)
        db.commit()
        db.refresh(fr)
        return fr.id


def _save_note(report_id: int, note: str) -> None:
    from ..db.session import SessionLocal
    from ..db.models import FeedbackReport
    with SessionLocal() as db:
        fr = db.get(FeedbackReport, report_id)
        if fr:
            fr.note = note
            db.commit()


@router.message(F.chat.type == "private", ((F.text & ~F.text.startswith("/")) | F.caption))
async def on_admin_forward(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = message.text or message.caption or ""
    # A text reply to a "logged" confirmation is the free-text note for that report.
    if message.text and message.reply_to_message:
        rid = _awaiting_note.pop((message.from_user.id, message.reply_to_message.message_id), None)
        if rid is not None:
            _save_note(rid, message.text)
            await message.reply("✅ Note added. Thanks.")
            return

    from .spam_detector import classify_spam  # lazy: avoids an import cycle
    reason = classify_spam(text, key=(message.chat.id, message.from_user.id))
    verdict = f"🔴 My verdict: spam — {reason}" if reason else "🟢 My verdict: not spam"
    sent = await message.reply(
        f"{verdict}\n\nIf I got it wrong, tap the button that's actually true:",
        reply_markup=_fb_keyboard(bool(reason)),
    )
    target_id, target_name = _forward_sender(message)
    _fb_pending[(message.from_user.id, sent.message_id)] = {
        "text": text,
        "verdict": reason or "clean",
        "cands": patterns.extract_keywords(text),
        "target_id": target_id,
        "target_name": target_name,
    }


@router.callback_query(F.data.startswith("fb:"))
async def on_fb_action(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("Not authorized.")
        return
    key = (cb.from_user.id, cb.message.message_id)
    state = _fb_pending.get(key)
    if not state:
        await cb.answer("Expired — forward the message again.")
        return
    action = cb.data.split(":", 1)[1]

    if action == "x":
        _fb_pending.pop(key, None)
        await cb.message.edit_text("Closed.")
        await cb.answer()
        return

    if action == "acct":
        await _flag_account(cb, state)
        return

    if action == "teach":
        cands = state["cands"]
        if not cands:
            await cb.answer("No keywords to teach from this one.", show_alert=True)
            return
        tstate = {
            "cands": cands, "sel": set(range(len(cands))),
            "cat": "inappropriate" if state["verdict"] == "inappropriate" else "ads",
            "group_id": None,
        }
        _pending[key] = tstate          # hand off to the existing teach flow (lp:*)
        _fb_pending.pop(key, None)
        await cb.message.edit_text("Teach keywords from this message?",
                                   reply_markup=_keyboard(tstate))
        await cb.answer()
        return

    # fp / fn -> persist a feedback report, then invite an optional note.
    label = "false_positive" if action == "fp" else "false_negative"
    rid = _save_feedback(cb.from_user.id, state["text"], state["verdict"], label)
    _fb_pending.pop(key, None)
    _awaiting_note[key] = rid           # admin replies to THIS message to add a note
    human = "not spam (I wrongly flagged it)" if action == "fp" else "spam (I missed it)"
    await cb.message.edit_text(
        f"✅ Logged as {human}.\nVerdict was: {state['verdict']}.\n\n"
        f"Reply to this message to add a note (optional)."
    )
    await cb.answer("Logged — thank you!")


async def _flag_account(cb: CallbackQuery, state: dict) -> None:
    """Flag the forwarded message's SENDER as a suspicious profile (not the
    message). We never auto-ban — the account is recorded + watchlisted, and
    admins are alerted to decide. Re-runs the profile check for extra signal."""
    target_id, target_name = state.get("target_id"), state.get("target_name")
    if target_id is None and not target_name:
        await cb.answer(
            "Forward the user's actual message (not a copy) so I can see whose account it is.",
            show_alert=True)
        return
    rid = _save_feedback(cb.from_user.id, state["text"], state["verdict"],
                         "suspicious_account", target_id, target_name)
    key = (cb.from_user.id, cb.message.message_id)
    _fb_pending.pop(key, None)
    _awaiting_note[key] = rid

    profile = None
    if target_id is not None:
        watchlist.add(target_id, None)
        try:
            from types import SimpleNamespace
            from .profile_checker import check_profile  # lazy: avoids import cycle
            profile = await check_profile(cb.bot, SimpleNamespace(id=target_id))
        except Exception as e:
            logging.warning(f"flag-account profile check failed: {e}")

    who = target_name or "unknown"
    if target_id is not None:
        who += f" (id {target_id})"
    tail = ("⚠️ No action taken automatically. I'll alert you when this account "
            "posts in a protected group so you can decide."
            if target_id is not None else
            "⚠️ Sender hidden by forward privacy — recorded by name only, can't auto-watch.")
    await send_to_admins(cb.bot, (
        f"🕵️ Account flagged as suspicious profile\n"
        f"👤 {who}\n"
        f"🙋 Flagged by: @{cb.from_user.username or cb.from_user.id}\n"
        f"📝 Profile check: {profile or 'no automated signal'}\n"
        f"📄 Their message: {(state['text'] or '[media]')[:200]}\n"
        f"{tail}"
    ))
    head = "✅ Account flagged." if target_id is not None else \
        "✅ Flagged by name (sender hidden — can't watch by id)."
    await cb.message.edit_text(f"{head}\nReply to this message to add a note (optional).")
    await cb.answer("Flagged — thank you!")


async def notify_admins_watched(bot, message: Message) -> None:
    """A watchlisted (admin-flagged) account posted in a protected group. The
    message itself isn't spam, so we don't touch it — we ask admins to decide."""
    body = (message.text or message.caption or "[media]")[:200]
    await notify_group(bot, message.chat.id, (
        f"🕵️ Flagged account is active\n"
        f"👤 {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"🆔 {message.from_user.id}\n"
        f"💬 Group: {message.chat.title or message.chat.id}\n"
        f"📄 Message (not auto-removed): {body}\n"
        f"Decide below — Ban or leave them."
    ), reply_markup=action_keyboard(message.chat.id, message.from_user.id))


@router.message(Command("feedback"))
async def handle_feedback_list(message: Message) -> None:
    """Admin-only: review the last few reported misclassifications."""
    if message.chat.type != "private" or not _is_admin(message.from_user.id):
        return
    from ..db.session import SessionLocal
    from ..db.models import FeedbackReport
    with SessionLocal() as db:
        rows = db.query(FeedbackReport).order_by(FeedbackReport.id.desc()).limit(10).all()
    if not rows:
        await message.reply("No feedback reports yet. Forward a misclassified message to add one.")
        return
    icon = {"false_positive": "🚩", "false_negative": "🐛", "suspicious_account": "🕵️"}
    lines = [f"📋 Last {len(rows)} feedback reports:\n"]
    for r in rows:
        if r.label == "suspicious_account":
            who = r.target_name or "?"
            if r.target_user_id:
                who += f" (id {r.target_user_id})"
            line = f"🕵️ #{r.id} account: {who}"
        else:
            txt = (r.message_text or "")[:80]
            line = f"{icon.get(r.label, '•')} #{r.id} [{r.bot_verdict}] {txt}"
        if r.note:
            line += f"\n   📝 {r.note[:120]}"
        lines.append(line)
    await message.reply("\n".join(lines))


@router.callback_query(F.data.startswith("lp:"))
async def on_lp_action(cb: CallbackQuery) -> None:
    # Authorization via state ownership: only the user who created the pending
    # entry (operator in DM, or group admin via /teach) can match their own key.
    key = (cb.from_user.id, cb.message.message_id)
    state = _pending.get(key)
    if not state:
        await cb.answer("Expired — forward the message again.")
        return

    parts = cb.data.split(":", 2)[1:]
    kind = parts[0]
    if kind == "t":
        state["sel"] ^= {int(parts[1])}
        await cb.message.edit_reply_markup(reply_markup=_keyboard(state))
    elif kind == "c":
        state["cat"] = parts[1]
        await cb.message.edit_reply_markup(reply_markup=_keyboard(state))
    elif kind == "x":
        _pending.pop(key, None)
        await cb.message.edit_text("Cancelled.")
    elif kind == "save":
        chosen = [state["cands"][i] for i in sorted(state["sel"])]
        if not chosen:
            await cb.answer("Nothing selected.")
            return
        n = patterns.add_learned(chosen, state["cat"], cb.from_user.id,
                               group_id=state.get("group_id"))
        _pending.pop(key, None)
        await cb.message.edit_text(f"✅ Added {n} '{state['cat']}' pattern(s).")
    await cb.answer()


# kind -> the group command that sets it, and its display name
_KEY_KIND_COMMANDS = {"gemini": "setkey", "vt": "setvtkey"}
_KEY_KIND_NAMES = {"gemini": "Gemini", "vt": "VirusTotal"}


@router.message(Command("start"))
async def handle_start(message: Message, command: CommandObject) -> None:
    payload = command.args or ""
    for kind, cmd in _KEY_KIND_COMMANDS.items():
        prefix = f"{cmd}-"
        if payload.startswith(prefix):
            try:
                chat_id = int(payload[len(prefix):])
            except ValueError:
                break
            await _start_setkey(message, chat_id, kind)
            return
    await message.reply(copy.START_TEXT, disable_web_page_preview=True)


async def _start_setkey(message: Message, chat_id: int, kind: str = "gemini") -> None:
    """Deep-link landing (private chat): an admin tapped the group's 'Set up key'
    button. Verify they administer that group, then DM the key-entry link and
    remove the group prompt."""
    from ..core import keys
    user_id = message.from_user.id
    # The shared-key scope belongs to /globalkey and /globalvtkey alone; a
    # hand-built deep link (?start=setkey-0) must never reach it through here.
    if chat_id == keys.GLOBAL_SCOPE or not groups.is_allowed(chat_id):
        await message.reply("That group isn't protected yet — run /enable there first.")
        return
    if user_id not in await _group_admin_ids(message.bot, chat_id) and not _is_admin(user_id):
        await message.reply(f"Only an admin of that group can set its {_KEY_KIND_NAMES[kind]} key.")
        return
    if not await _deliver_setkey_link(message.bot, chat_id, user_id, kind=kind):
        await message.reply(f"Couldn't send the setup link — try /{_KEY_KIND_COMMANDS[kind]} again.")
        return
    pid = _setkey_prompts.pop((chat_id, kind), None)  # clean up the group button
    if pid:
        try:
            await message.bot.delete_message(chat_id, pid)
        except Exception:
            pass


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    for part in copy.HELP_PARTS:
        await message.reply(part, disable_web_page_preview=True)


@router.message(Command("privacy"))
async def handle_privacy_command(message: Message) -> None:
    await message.reply(copy.PRIVACY_TEXT, disable_web_page_preview=True)


@router.message(Command("tokens"))
async def handle_tokens_command(message: Message) -> None:
    """Token usage: previous day / 7 days / 30 days, with model, tokens and USD cost.
    In a group: that group's numbers (admins/operator). In operator DM: all groups."""
    chat = message.chat
    if chat.type in ("group", "supergroup"):
        if not groups.is_allowed(chat.id):
            return
        if not message.from_user or not await _is_group_admin(message):
            await reply_temp(message, _NOT_AUTHORIZED)
            await delete_command(message)
            return
        await message.reply(usage.tokens_report(chat.id))   # persists — a table needs reading
        await delete_command(message)
        return
    # Private chat: operator gets the global, per-group breakdown.
    if not _is_admin(message.from_user.id):
        await message.reply("Run /tokens inside a group you administer to see its usage.")
        return
    await message.reply(usage.tokens_report(None))


@router.message(Command("stats"))
async def handle_stats_command(message: Message) -> None:
    """Operator-only (private DM): group roster + spam/ban activity across all
    groups. Groups are the operator's whole deployment, so this stays owner-gated."""
    if message.chat.type in ("group", "supergroup"):
        return  # operator stat, not a per-group command
    if not _is_admin(message.from_user.id):
        await message.reply("This command is for the bot operator.")
        return
    titles = await stats.resolve_titles(message.bot, groups.allowed_ids())
    await message.reply(stats.report(titles))


@router.message(Command("globalkey"))
async def handle_globalkey_command(message: Message, command: CommandObject) -> None:
    """Operator-only (private DM): one shared Gemini key for every protected group
    without a key of its own; a group's /setkey key always wins over it.
      /globalkey        status
      /globalkey set    DM a one-time link to the key form (the /setkey form)
      /globalkey off    remove it — keyless groups drop back to regex-only
    Entered on the web form, never in chat: a bot can't delete a user's message in
    a private chat, so a pasted key would sit in Telegram history for good."""
    await _shared_key_command(message, command, "gemini")


@router.message(Command("globalvtkey"))
async def handle_globalvtkey_command(message: Message, command: CommandObject) -> None:
    """Operator-only (private DM): /globalkey for the VirusTotal key that link
    checks use in groups without a /setvtkey key of their own."""
    await _shared_key_command(message, command, "vt")


async def _shared_key_command(message: Message, command: CommandObject, kind: str) -> None:
    from ..core import ai_settings, crypto, keys
    from ..core.config import BASE_URL, VIRUSTOTAL_API_KEY
    cmd = "globalkey" if kind == "gemini" else "globalvtkey"
    name = _KEY_KIND_NAMES[kind]
    if message.chat.type in ("group", "supergroup"):
        await delete_command(message)   # never discuss a shared key in a group
        return
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply("This command is for the bot operator.")
        return
    arg = (command.args or "").strip().lower()

    if arg == "set":
        if not crypto.available() or not BASE_URL:
            await message.reply("⚠️ Kalit saqlash sozlanmagan: KEY_ENCRYPTION_SECRET va BASE_URL kerak.")
            return
        if not await _deliver_setkey_link(message.bot, keys.GLOBAL_SCOPE, message.from_user.id,
                                          what=f"the shared {name} key for all groups", kind=kind):
            await message.reply("Havolani yuborib bo'lmadi — qayta urinib ko'ring.")
        return

    ids = groups.allowed_ids()
    if kind == "gemini":
        # Only groups with AI switched on (/ai) actually spend the shared key.
        users = sum(1 for cid in ids if not keys.has_key(cid) and ai_settings.is_enabled(cid))
        users_note = "qolganlarida o'z kaliti bor yoki AI o'chirilgan"
        without = "faqat regex bilan ishlaydi"
    else:
        users = sum(1 for cid in ids if not keys.has_key(cid, "vt"))
        users_note = "qolganlarida o'z kaliti bor"
        without = ("serverdagi .env kalitidan foydalanadi" if VIRUSTOTAL_API_KEY
                   else "havolalarni VirusTotal'siz tekshiradi")

    if arg == "off":
        if keys.delete_key(keys.GLOBAL_SCOPE, kind):
            await message.reply(f"🗑 Umumiy {name} kaliti o'chirildi. O'z kaliti yo'q guruhlar endi {without}.")
        else:
            await message.reply(f"Umumiy {name} kaliti o'rnatilmagan edi.")
        return

    info = keys.key_info(keys.GLOBAL_SCOPE, kind)
    if info:
        by, at = info
        when = f"{at:%Y-%m-%d %H:%M} UTC" if at else "?"
        status = (f"🔑 Umumiy {name} kaliti: YOQILGAN\n"
                  f"O'rnatgan: {by}, {when}\n"
                  f"Ishlatayotgan guruhlar: {users} / {len(ids)} ({users_note})")
    else:
        status = (f"🔑 Umumiy {name} kaliti: O'CHIQ\n"
                  f"O'z kaliti yo'q guruhlar: {users} / {len(ids)} — ular {without}")
    if kind == "vt" and VIRUSTOTAL_API_KEY:
        status += "\nZaxira: serverdagi .env faylida ham VirusTotal kaliti bor."

    tips = [f"/{cmd} set — o'rnatish yoki almashtirish (bir martalik havola)",
            f"/{cmd} off — o'chirish"]
    if kind == "gemini":
        tips.append("/ai — qaysi guruhlarda AI ishlashini tanlash")
        warn = ("⚠️ /enable ni istalgan guruh admini qila oladi — o'z kaliti yo'q har bir guruhning "
                "AI'si shu kalit hisobidan ishlaydi. Guruhlar bo'yicha sarfni /tokens da ko'rasiz.")
    else:
        warn = ("⚠️ VirusTotal'ning bepul limiti bitta kalit uchun kuniga 500 so'rov. Guruhlar "
                "ko'paysa, ular /setvtkey bilan o'z kalitini qo'shgani ma'qul.")
    await message.reply(f"{status}\n\n" + "\n".join(tips) + f"\n\n{warn}")


# --- Operator AI switch (/ai) ---------------------------------------------------

_AI_STATUS = {
    "own": ("✅", "AI ishlayapti (guruhning o'z kaliti)"),
    "global": ("✅", "AI ishlayapti (umumiy kalit)"),
    "nokey": ("⚠️", "yoqilgan, lekin kalit yo'q — ishlamayapti"),
    "off": ("⛔", "AI o'chirilgan"),
}


def _short(title: str, limit: int = 28) -> str:
    return title if len(title) <= limit else title[: limit - 1] + "…"


async def _ai_panel(bot) -> tuple:
    """The /ai view: the default, the shared-key state, and one status line plus
    one toggle button per protected group."""
    from ..core import ai_settings, keys
    ids = sorted(groups.allowed_ids())
    titles = await stats.resolve_titles(bot, ids)
    statuses = {cid: ai_settings.status(cid) for cid in ids}
    default = "✅ yoqilgan" if ai_settings.default_enabled() else "⛔ o'chirilgan"
    shared = "🔑 o'rnatilgan" if keys.get_global_key() else "❌ yo'q (/globalkey set)"
    lines = [
        "🤖 AI moderatsiya — faqat 18+ kontentni tekshiradi",
        f"Standart: {default} — yangi guruhlar shunga ergashadi",
        f"Umumiy kalit: {shared}",
        "",
    ]
    rows = []
    if not ids:
        lines.append("Hali himoyalangan guruh yo'q.")
    for cid in ids:
        icon, label = _AI_STATUS[statuses[cid]]
        title = titles.get(cid, str(cid))
        lines.append(f"{icon} {title} — {label}")
        action = "✅ Yoqish" if statuses[cid] == "off" else "⛔ O'chirish"
        rows.append([InlineKeyboardButton(
            text=f"{action}: {_short(title)}", callback_data=f"ai:g:{cid}")])
    rows.append([
        InlineKeyboardButton(text="✅ Hammasida yoqish", callback_data="ai:all:1"),
        InlineKeyboardButton(text="⛔ Hammasida o'chirish", callback_data="ai:all:0"),
    ])
    if "nokey" in statuses.values():
        lines += ["", "⚠️ Kaliti yo'q guruhlarda AI yoqilgan bo'lsa ham ishlamaydi. "
                      "Umumiy kalit o'rnatish: /globalkey set"]
    lines += ["", "AI o'chirilgan guruhlarda ham aniq 18+ profil rasmlari va "
                  "18+ havolali bio'lar tekshirilaveradi."]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("ai"))
async def handle_ai_command(message: Message) -> None:
    """Operator-only (private DM): choose where the paid AI layer runs — every
    group at once, or group by group. Groups enabled later follow the default."""
    if message.chat.type in ("group", "supergroup"):
        await delete_command(message)
        return
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply("This command is for the bot operator.")
        return
    text, kb = await _ai_panel(message.bot)
    await message.reply(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ai:"))
async def on_ai_toggle(cb: CallbackQuery) -> None:
    from ..core import ai_settings
    if not _is_admin(cb.from_user.id):
        await cb.answer("Not authorized.")
        return
    parts = cb.data.split(":")
    try:
        if parts[1] == "all":
            on = parts[2] == "1"
            ai_settings.set_all(on)
            note = "AI hammasida yoqildi" if on else "AI hammasida o'chirildi"
        elif parts[1] == "g":
            chat_id = int(parts[2])
            on = not ai_settings.is_enabled(chat_id)
            ai_settings.set_group(chat_id, on)
            note = "Yoqildi" if on else "O'chirildi"
        else:
            await cb.answer()
            return
    except (IndexError, ValueError):
        await cb.answer()
        return
    except Exception as e:
        logging.error(f"/ai toggle failed ({cb.data}): {e}")
        await cb.answer("Saqlab bo'lmadi — qayta urinib ko'ring.", show_alert=True)
        return
    text, kb = await _ai_panel(cb.bot)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        logging.info(f"/ai panel refresh skipped: {e}")   # e.g. "message is not modified"
    await cb.answer(note)


_NOT_AUTHORIZED = "❌ Only group admins can use this."


@router.message(Command("enable"))
async def handle_enable(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Run /enable inside the group you want to protect.")
        return
    if not await _is_group_admin(message):
        await reply_temp(message, _NOT_AUTHORIZED)
        await delete_command(message)
        return
    # Need admin rights (delete + ban) to actually moderate — refuse to pretend otherwise.
    if not await _bot_can_moderate(message.bot, message.chat.id):
        await reply_temp(
            message,
            "⚠️ Make me an admin first with **Delete messages** and **Ban users** rights, then run /enable again.")
        await delete_command(message)
        return
    owner = message.from_user.id if message.from_user else 0
    # Abuse cap: limit groups one non-operator admin can enable (already-enabled groups re-enable freely).
    if (not _is_admin(owner) and not groups.is_allowed(message.chat.id)
            and groups.count_by(owner) >= MAX_GROUPS_PER_OWNER):
        await reply_temp(
            message,
            f"⚠️ You've reached the limit of {MAX_GROUPS_PER_OWNER} protected groups. "
            "Disable one first, or contact the bot operator.")
        await delete_command(message)
        return
    groups.enable(message.chat.id, owner)
    from ..core import ai_settings, keys
    src = keys.key_source(message.chat.id)
    if not ai_settings.is_enabled(message.chat.id):
        ai_line = ("AI detection is switched off for this group by the bot operator. "
                   "Explicit profile photos and explicit bio links are still checked.")
    elif src == "own":
        ai_line = "AI detection is on with this group's own Gemini key."
    elif src == "global":
        ai_line = ("AI detection is on (the bot operator's shared key). An admin can run "
                   "/setkey to use the group's own Gemini key instead.")
    else:
        ai_line = ("AI detection is off until an admin runs /setkey with a Gemini key — "
                   "keyword rules are already active.")
    await reply_temp(message, "✅ This group is now protected.\n\n" + ai_line)
    await delete_command(message)


@router.message(Command("disable"))
async def handle_disable(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Run /disable inside the group.")
        return
    if not await _is_group_admin(message):
        await reply_temp(message, _NOT_AUTHORIZED)
        await delete_command(message)
        return
    groups.disable(message.chat.id)
    await reply_temp(message, "🛑 Protection disabled for this group.")
    await delete_command(message)


# Key-setup helpers ------------------------------------------------------------
_setkey_prompts: dict = {}  # (chat_id, kind) -> group-prompt message_id (cleaned up on use)
_bot_uname: list = []       # cache for the bot's @username


async def _bot_username(bot) -> str:
    if not _bot_uname:
        _bot_uname.append((await bot.get_me()).username)
    return _bot_uname[0]


async def _deliver_setkey_link(bot, chat_id: int, user_id: int, what: str = None,
                               kind: str = "gemini") -> bool:
    """Mint a one-time token for chat_id and DM the key-entry link to user_id.
    Returns False only if the DM itself couldn't be sent (user hasn't started me)."""
    from ..core import tokens
    from ..core.config import BASE_URL
    what = what or f"the group's {_KEY_KIND_NAMES[kind]} key"
    tok = tokens.mint(chat_id, user_id, kind)
    if not tok:
        try:
            await bot.send_message(
                user_id, f"Couldn't create a setup link — try /{_KEY_KIND_COMMANDS[kind]} again.")
        except Exception:
            return False
        return True
    link = f"{BASE_URL.rstrip('/')}/key?t={tok}"
    try:
        await bot.send_message(
            user_id,
            f"🔑 Open this link to set {what} (valid 15 min, one-time):\n{link}",
            disable_web_page_preview=True)
        return True
    except Exception:
        return False


@router.message(Command("setkey"))
async def handle_setkey_command(message: Message) -> None:
    """Group admins: store the group's own Gemini key (AI moderation)."""
    await _setkey_flow(message, "gemini")


@router.message(Command("setvtkey"))
async def handle_setvtkey_command(message: Message) -> None:
    """Group admins: store the group's own VirusTotal key, so its link checks don't
    share the operator's daily VirusTotal quota."""
    await _setkey_flow(message, "vt")


async def _setkey_flow(message: Message, kind: str) -> None:
    """Group-only and kept PRIVATE. Deletes the command on sight (no copycats).
    If I can already DM the admin, the link goes straight to their DM and nothing
    is posted in the group. If I can't DM them yet, I post ONE clean inline button
    that opens our private chat (deep link), then deliver the link there and remove
    the button. Non-admins / copycats are silently deleted."""
    from ..core import crypto
    from ..core.config import BASE_URL
    cmd, name = _KEY_KIND_COMMANDS[kind], _KEY_KIND_NAMES[kind]

    if message.chat.type not in ("group", "supergroup"):
        await message.reply(f"Use /{cmd} inside the group you want to protect.")
        return

    try:
        await message.bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logging.info(f"couldn't delete /{cmd} command in {message.chat.id}: {e}")

    if not groups.is_allowed(message.chat.id):
        return
    if not message.from_user or not await _is_group_admin(message):
        return  # copycat / non-admin: command already deleted, stay silent
    if not _setkey_limit.allow((message.from_user.id, kind)):
        return

    if not crypto.available() or not BASE_URL:
        try:
            await message.bot.send_message(
                message.from_user.id,
                f"⚠️ {name} key setup isn't configured on this bot yet. Contact the operator.")
        except Exception:
            pass
        return

    # Admin already started me -> deliver privately, nothing in the group.
    if await _deliver_setkey_link(message.bot, message.chat.id, message.from_user.id, kind=kind):
        return

    # Can't DM yet: post one clean deep-link button to open our private chat.
    uname = await _bot_username(message.bot)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"🔑 Set up {name} key (private)",
        url=f"https://t.me/{uname}?start={cmd}-{message.chat.id}")]])
    sent = await message.answer(
        f"{message.from_user.first_name}, tap to set this group's {name} key — "
        f"it opens a private chat with me, and this message will disappear.",
        reply_markup=kb)
    _setkey_prompts[(message.chat.id, kind)] = sent.message_id


async def _moderation_target(message: Message, usage: str):
    """Shared guards for /ban & /mute. Returns the target user, or None (replied)."""
    if message.chat.type not in ("group", "supergroup") or not groups.is_allowed(message.chat.id):
        return None
    if not await _is_group_admin(message):
        await reply_temp(message, "❌ Only group admins can use this.")
        return None
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await reply_temp(message, usage)
        return None
    return message.reply_to_message.from_user


@router.message(Command("ban"))
async def handle_ban_command(message: Message) -> None:
    target = await _moderation_target(message, "Reply to the user's message with /ban.")
    if not target:
        await delete_command(message)
        return
    try:
        await message.bot.ban_chat_member(message.chat.id, target.id)
        try:
            await message.bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
        await reply_temp(message, f"🔨 Banned {target.full_name}.")
        await notify_operator_action(
            message.bot, message.chat.id, target.id, "🔨 BAN (/ban buyrug'i)",
            "admin /ban buyrug'ini ishlatdi",
            by=f"@{message.from_user.username or message.from_user.id}")
    except Exception as e:
        await reply_temp(message, f"Couldn't ban (are they an admin?): {e}")
    await delete_command(message)


def _parse_mute_args(args: str | None) -> tuple[int, str | None]:
    """Parse /mute args into (hours, reason). Forms:
        (none)      -> 24h, no reason
        N           -> N hours, no reason
        N <reason>  -> N hours, with reason
        <reason>    -> 24h, with reason
    Hours are clamped to [1, 8760] (1 year)."""
    if not args or not args.strip():
        return 24, None
    parts = args.strip().split(maxsplit=1)
    if parts[0].isdigit():
        hours = max(1, min(8760, int(parts[0])))
        reason = parts[1].strip() if len(parts) > 1 else None
        return hours, (reason or None)
    return 24, args.strip()


async def announce_mute(bot, chat_id: int, name: str, hours: int, reason: str | None = None) -> None:
    """Post a short notice in the group when a user is muted. Reason is shown
    only when one was given (manual /mute reason, or an auto-detection reason)."""
    line = f"🔇 {name} was muted for {hours} hour{'s' if hours != 1 else ''}"
    if reason:
        line += f" due to {reason}"
    try:
        sent = await bot.send_message(chat_id, line + ".")
        autodelete(bot, chat_id, sent.message_id)
    except Exception as e:
        logging.warning(f"Mute announce failed in {chat_id}: {e}")


@router.message(Command("mute"))
async def handle_mute_command(message: Message, command: CommandObject) -> None:
    target = await _moderation_target(
        message, "Reply to a message with /mute, /mute <hours>, /mute <reason>, or /mute <hours> <reason>.")
    if not target:
        await delete_command(message)
        return
    hours, reason = _parse_mute_args(command.args)
    try:
        await message.bot.restrict_chat_member(
            message.chat.id, target.id, permissions=_MUTED,
            until_date=datetime.now() + timedelta(hours=hours),
        )
    except Exception as e:
        await reply_temp(message, f"Couldn't mute (are they an admin?): {e}")
        await delete_command(message)
        return
    await announce_mute(message.bot, message.chat.id, target.full_name, hours, reason)
    await delete_command(message)


# NOTE: /teach and /flag are not yet added to the command menu or /help — deferred to Phase 6.

@router.message(Command("teach"))
async def handle_teach_command(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup") or not groups.is_allowed(message.chat.id):
        return
    if not await _is_group_admin(message):
        await message.reply("❌ Only group admins can use this.")
        return
    replied = message.reply_to_message
    text = (replied.text or replied.caption) if replied else None
    if not text:
        await message.reply("Reply to a spam message with /teach to learn its keywords for this group.")
        return
    cands = patterns.extract_keywords(text)
    if not cands:
        await message.reply("No keywords to teach from that message.")
        return
    state = {"cands": cands, "sel": set(range(len(cands))), "cat": "ads", "group_id": message.chat.id}
    sent = await message.reply("Teach keywords for THIS group?", reply_markup=_keyboard(state))
    _pending[(message.from_user.id, sent.message_id)] = state


@router.message(Command("flag"))
async def handle_flag_command(message: Message) -> None:
    target = await _moderation_target(
        message,
        "Reply to a user's message with /flag to flag their account as a suspicious bot profile for this group.")
    if not target:
        await delete_command(message)
        return
    watchlist.add(target.id, message.chat.id)
    replied = message.reply_to_message
    body = (replied.text or replied.caption or "") if replied else ""
    _save_feedback(message.from_user.id, body, "flagged", "suspicious_account",
                   target_id=target.id, target_name=target.full_name, group_id=message.chat.id)
    await reply_temp(
        message,
        f"🕵️ Flagged {target.full_name}'s account for this group. "
        f"I'll alert admins if they post again instead of auto-banning.")
    await delete_command(message)


# --- User reports: reply with JUST "spam"/"ban"/"admin" (or /report) -----------
# Must be a standalone trigger word so normal sentences that merely mention
# "ban"/"admin" don't fire a bogus report.
_setkey_limit = RateLimiter(limit=3, window=3600.0)  # per (admin, key kind) / hour

_REPORT_WORDS = {"spam", "ban", "admin", "report", "shikoyat", "спам", "бан", "админ", "жалоба"}
_report_limit = RateLimiter(limit=3, window=60.0)  # per reporter / minute


def _is_report(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    if t.startswith("/report"):
        return True
    return t.strip("!.,?@/ ") in _REPORT_WORDS


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.text.func(_is_report),
)
async def handle_report(message: Message) -> None:
    if not groups.is_allowed(message.chat.id):
        return
    reporter = message.from_user
    if not reporter:
        return  # channel-sender "report" — nothing actionable
    reported = message.reply_to_message
    target = reported.from_user
    if target and target.is_bot:
        return  # don't report bots (including me)
    if not _report_limit.allow(reporter.id):
        return  # ignore report floods
    body = reported.text or reported.caption or "[no text / media]"
    text = (
        "⚠️ User report\n"
        f"👮 Reporter: {reporter.full_name} (@{reporter.username or 'none'})\n"
        f"💬 Group: {message.chat.title or message.chat.id}\n"
        f"🙋 Reported: {target.full_name if target else 'unknown'} "
        f"(@{target.username if target and target.username else 'none'})"
        f"{' 🆔 ' + str(target.id) if target else ''}\n"
        f"📝 Message: {body[:300]}\n"
        f"🗣 Report: {message.text[:150]}"
    )
    kb = action_keyboard(message.chat.id, target.id) if target else None
    await notify_group(message.bot, message.chat.id, text, reply_markup=kb)
    await reply_temp(message, "✅ Adminlarga yuborildi / Reported to admins.")


@router.my_chat_member()
async def on_added_to_group(event: ChatMemberUpdated) -> None:
    if event.chat.type not in ("group", "supergroup"):
        return
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    # Only on transition INTO the group (added/joined), not every promote/demote.
    if old not in ("left", "kicked") or new not in ("member", "administrator"):
        return
    adder = event.from_user
    if not adder:
        return
    try:
        await event.bot.send_message(adder.id, copy.SETUP_TEXT, disable_web_page_preview=True)
    except Exception:
        # adder hasn't started the bot (Telegram privacy) — leave a short in-group hint
        try:
            await event.bot.send_message(
                event.chat.id,
                "👋 I'm added. An admin: make me admin (Delete messages + Ban users), then send /enable. /help for details.")
        except Exception as e:
            logging.warning(f"onboarding hint failed in {event.chat.id}: {e}")


def register_admin_handlers(dp) -> None:
    dp.include_router(router)
