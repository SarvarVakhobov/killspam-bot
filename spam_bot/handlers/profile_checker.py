"""Scan new members' bio + profile photo on join.

Order is cheapest-first: bio regex (free) -> local NudeNet (no API). Only a
clearly-explicit photo acts; ambiguous photos take no action (blocking on
uncertainty muted legit users). ponytail: join-only trigger means each account is
scanned once; pre-existing members are caught by message-content detection.
"""
import logging

from aiogram import Router, F
from aiogram.types import ChatJoinRequest, Message

from ..core import groups, nsfw, patterns
from .spam_detector import block_user, classify_spam
from .admin_notifier import action_keyboard, notify_group

router = Router()


# Scan more than the first profile photo: a common tactic is a clean first
# picture with explicit ones behind it. ponytail: cap at 10 most-recent photos
# to bound downloads/NudeNet runs — raise if spammers start padding past that.
_MAX_PROFILE_PHOTOS = 10


def is_severe(reason) -> bool:
    """Hard 18+ signals → ban + delete: a clearly-explicit profile photo or a bio
    linking explicit content. Softer verdicts (the AI on a bio, an admin-taught
    keyword) stay a 24h mute + admin review. Ambiguous photos are never flagged at
    all, so they never reach here."""
    if not reason:
        return False
    return ("flagged explicit (NudeNet)" in reason
            or reason == "profile bio links to explicit/adult content")


async def check_bio(bot, user_id, group_id=None) -> str | None:
    """Bio-only scan — one get_chat call, no photo downloads. The #1 escape tactic
    is a clean first message with the payload in the bio. A link next to explicit
    terms is a hard block (ban); a link to an app file (.apk/.exe) mutes. A bio that
    merely links the member's own channel or site is normal: it goes to the AI,
    which judges only 18+ content and runs only where AI is switched on and a key
    exists. Cheap enough to run on a sender's first message, not just at join."""
    try:
        bio = (await bot.get_chat(user_id)).bio or ""
    except Exception:
        return None
    if not bio:
        return None
    if patterns.has_explicit_link(bio):
        return "profile bio links to explicit/adult content"
    if patterns.has_malware_link(bio):
        return "profile bio links a downloadable app (likely malware)"
    reason = classify_spam(bio, group_id=group_id)
    if reason:
        return f"profile bio flagged ({reason})"
    return None


async def check_profile(bot, user, group_id=None) -> str | None:
    reason = await check_bio(bot, user.id, group_id)
    if reason:
        return reason

    try:
        photos = await bot.get_user_profile_photos(user.id, limit=_MAX_PROFILE_PHOTOS)
    except Exception as e:
        logging.warning(f"Couldn't fetch profile photos for {user.id}: {e}")
        return None

    for i, sizes in enumerate(photos.photos):  # one entry per photo; [-1] = largest size
        try:
            f = await bot.get_file(sizes[-1].file_id)
            buf = await bot.download_file(f.file_path)
            verdict = nsfw.check(buf.read())
        except Exception as e:
            logging.warning(f"Profile photo #{i + 1} check failed for {user.id}: {e}")
            continue  # one bad photo shouldn't skip the rest
        if verdict is True:
            return f"profile photo #{i + 1} flagged explicit (NudeNet)"
        # Ambiguous (None) or clean (False) -> NO action. We only act on a clearly
        # explicit verdict; blocking on uncertain photos muted legit users.
    return None


@router.message(F.new_chat_members)
async def on_join(message: Message) -> None:
    if not groups.is_allowed(message.chat.id):
        return  # cost guard: only scan joins in authorized groups

    # Tidy up the "X joined the group" service message (needs delete permission).
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Couldn't delete join message: {e}")

    for user in message.new_chat_members:
        if user.is_bot:
            continue
        reason = await check_profile(message.bot, user, message.chat.id)
        if not reason:
            continue
        severe = is_severe(reason)
        await block_user(message.bot, message.chat.id, user.id, reason,
                         user_type="bot" if severe else "human",
                         is_permanent=severe, ban=severe)
        tail = ("⛔ Banned — profile flagged (explicit photo or 18+ link)."
                if severe else "⚠️ Muted 24h pending review — Ban or Unmute below.")
        await notify_group(message.bot, message.chat.id, (
            f"🚨 Suspicious profile on join\n"
            f"👤 {user.full_name} (@{user.username or 'none'})\n"
            f"🆔 {user.id}\n"
            f"💬 {message.chat.title or message.chat.id}\n"
            f"📝 {reason}\n"
            f"{tail}"
        ), reply_markup=action_keyboard(message.chat.id, user.id))


@router.message(F.left_chat_member)
async def on_leave(message: Message) -> None:
    if not groups.is_allowed(message.chat.id):
        return
    # Tidy up the "X left the group" / "X was removed" service message.
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Couldn't delete leave message: {e}")


@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest) -> None:
    """Guard-mode gate: silently approve clean profiles, decline spam ones.
    No challenge/button — zero friction for real users."""
    if not groups.is_allowed(req.chat.id):
        await req.approve()  # not a protected group — don't gate, just let them in
        return
    reason = await check_profile(req.bot, req.from_user, req.chat.id)
    if not reason:
        await req.approve()
        return
    await req.decline()
    u = req.from_user
    await notify_group(req.bot, req.chat.id, (
        f"🚫 Join request auto-declined\n"
        f"👤 {u.full_name} (@{u.username or 'none'})\n"
        f"🆔 {u.id}\n"
        f"💬 {req.chat.title or req.chat.id}\n"
        f"📝 {reason}\n"
        f"(Add them manually if this was a mistake.)"
    ))


def register_profile_handlers(dp) -> None:
    dp.include_router(router)
