import json
import logging
import time
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.types import ChatPermissions, Message

from ..core import ai_settings, groups, keys, patterns, usage, watchlist
from ..core.config import GEMINI_MODEL
from ..core.prompts import SPAM_SYSTEM_INSTRUCTION
from ..core.ratelimit import RateLimiter
from ..db.session import SessionLocal
from ..db.models import BlockedUser, SpamReport
from .admin_notifier import (
    announce_mute, notify_admins, notify_admins_watched, notify_operator_action,
)

# Import Gemini AI (optional — regex layer works without it).
# Loud on failure: a silent miss here disables all semantic detection.
try:
    from google import genai  # type: ignore  (package: google-genai)
except Exception as _e:
    genai = None  # type: ignore
    logging.warning(f"google-genai unavailable — AI moderation DISABLED: {_e}")

router = Router()

_client_cache: dict = {}  # sha256(key) -> genai.Client


def _get_gemini_client(group_id=None):
    # A group's own BYOK key first; failing that, the operator's shared key
    # (/globalkey). Neither -> no AI (regex layer still runs).
    api_key, _source = keys.resolve_key(group_id)
    if not api_key or genai is None:
        return None
    import hashlib
    h = hashlib.sha256(api_key.encode()).hexdigest()
    client = _client_cache.get(h)
    if client is None:
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logging.error(f"Failed to create Gemini client: {e}")
            return None
        _client_cache[h] = client
    return client


def _record_usage(response, group_id) -> None:
    """Pull token counts off a Gemini response and store them (best-effort —
    never let accounting break classification)."""
    try:
        um = getattr(response, "usage_metadata", None)
        if um is None:
            return
        prompt = getattr(um, "prompt_token_count", 0) or 0
        completion = getattr(um, "candidates_token_count", 0) or 0
        total = getattr(um, "total_token_count", 0) or (prompt + completion)
        usage.record(group_id, GEMINI_MODEL, prompt, completion, total)
    except Exception as e:
        logging.warning(f"token usage record skipped: {e}")


def _gemini_classify(text: str, client, group_id=None) -> str | None:
    """One Gemini call -> 'adult' | None. The AI layer now judges ONLY sexual/
    flirtatious content; ads/insults are handled elsewhere or allowed.
    Records token usage (best-effort) against the group it ran for — whether its
    own key or the operator's shared key paid, /tokens shows who consumed what."""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=text[:4096],  # cap user text (prompt-injection / cost guard)
            config={
                "system_instruction": SPAM_SYSTEM_INSTRUCTION,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_budget": 0},  # ~2x faster, no accuracy loss (benchmarked)
            },
        )
        _record_usage(response, group_id)
        data = json.loads(response.text)
        if isinstance(data, dict) and data.get("spam"):
            return "adult"  # AI layer only classifies sexual/flirtatious content now
    except Exception as e:
        logging.error(f"Gemini classify failed: {e}")
    return None


# Budget the paid Gemini layer (CSO audit: unbounded API calls). Regex always
# runs, so moderation coverage is unaffected when the budget is exhausted.
_user_budget = RateLimiter(limit=10, window=30.0)     # per (chat, user) / 30s
_global_budget = RateLimiter(limit=120, window=60.0)  # all users / minute

# Don't re-alert admins on every message from a watchlisted account — once an
# hour per (chat, user) is enough for them to decide.
_watch_alert = RateLimiter(limit=1, window=3600.0)

# First-message profile scan: remember which (chat, user) we've already scanned so
# the get_chat / photo download runs at most once per sender. Catches link-joiners
# whose profile was never scanned at join (public-group link joins emit no
# new_chat_members event). In-memory + bounded; a restart re-scans, which is cheap.
_profile_checked: set = set()
_PROFILE_CHECK_CAP = 100_000


def _classify(text: str, key, group_id=None) -> tuple[str | None, str]:
    reason = patterns.classify(text, group_id)
    if reason:
        return reason, "regex"
    # Operator switch (/ai). Checked before the budgets, so a switched-off group
    # doesn't spend rate-limit slots it will never use.
    if group_id is not None and not ai_settings.is_enabled(group_id):
        return None, "skipped:ai-off"
    if key is not None and not _user_budget.allow(key):
        return None, "skipped:user-ratelimit"
    if not _global_budget.allow("global"):
        return None, "skipped:global-ratelimit"
    client = _get_gemini_client(group_id)
    if not client:
        return None, "skipped:no-AI"
    return _gemini_classify(text, client, group_id), "gemini"


def classify_spam(text: str, key=None, group_id=None) -> str | None:
    """Free regex/keyword layer first; one rate-limited Gemini call if clean."""
    reason, via = _classify(text, key, group_id)
    # Diagnostic: text + verdict + how it was decided, so the logs are debuggable.
    logging.info(f"CLASSIFY result={reason or 'clean'} via={via} text={text[:200]!r}")
    return reason


def is_bot_account(message: Message) -> bool:
    """True only for actual Telegram bot accounts. A single flagged message now
    gives a human a recoverable 24h mute + admin alert, never an auto permanent
    ban — a false positive must be undoable. Permanent bans stay reserved for
    severe 18+ profile hits (an explicit photo or an explicit-link bio).
    ponytail: dropped the flirting-keyword + short-username heuristics; both
    permanently banned legitimate users on harmless messages."""
    return bool(message.from_user and message.from_user.is_bot)


def detect_explicit_content(image_data: bytes) -> bool:
    """Explicit-image check via the local NudeNet model."""
    from ..core import nsfw
    return nsfw.check(image_data) is True


_RESTRICTED = ChatPermissions(
    can_send_messages=False, can_send_media_messages=False,
    can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False, can_change_info=False,
    can_invite_users=False, can_pin_messages=False,
)


async def _delete_message_safe(message: Message) -> None:
    try:
        await message.bot.delete_message(message.chat.id, message.message_id)
        logging.info(f"Deleted spam message {message.message_id}")
    except Exception as e:
        logging.warning(f"Failed to delete message {message.message_id}: {e}")


async def block_user(bot, chat_id: int, user_id: int, reason: str,
                     user_type: str = "human", is_permanent: bool = False,
                     ban: bool = False) -> None:
    """Restrict a user (permanent or 24h) or hard-ban them, and log it. ban=True
    kicks the account out of the group — used for severe 18+ profile hits (an
    explicit photo or an explicit-link bio), which take priority over softer mutes."""
    try:
        expires_at = None if (is_permanent or ban) else datetime.now() + timedelta(hours=24)
        if ban:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        else:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id,
                permissions=_RESTRICTED, until_date=expires_at,
            )
        with SessionLocal() as db:
            db.add(BlockedUser(
                telegram_id=user_id, group_id=chat_id, reason=reason,
                user_type=user_type, is_permanent=is_permanent or ban, expires_at=expires_at,
            ))
            db.commit()
        logging.info(f"{'Banned' if ban else 'Blocked'} {user_id} ({user_type}, "
                     f"permanent={is_permanent or ban}): {reason}")
        # Every automated restriction funnels through here, so this one call gives
        # the operator a complete feed of who was actioned in which group.
        if ban:
            label = "🔨 BAN (guruhdan chiqarildi)"
        elif is_permanent:
            label = "🔇 DOIMIY OVOZSIZ"
        else:
            label = "🔇 OVOZSIZ (24 soat)"
        await notify_operator_action(bot, chat_id, user_id, label, reason, user_type)
    except Exception as e:
        logging.error(f"Failed to block user {user_id}: {e}")


async def _report_spam(message: Message, reason: str) -> None:
    try:
        with SessionLocal() as db:
            db.add(SpamReport(
                telegram_id=message.from_user.id, group_id=message.chat.id,
                message_text=message.text or message.caption or "", reason=reason,
            ))
            db.commit()
    except Exception as e:
        logging.error(f"Failed to report spam: {e}")


# Cache each group's admin ids so we don't call get_chat_administrators per message.
_admin_cache: dict = {}      # chat_id -> (set[admin_id], monotonic_ts)
_ADMIN_TTL = 300.0


async def _sender_is_admin(message: Message) -> bool:
    """True if the sender is an admin of the chat (cached ~5 min). Admins are
    never moderated — deleting an admin's message would be a false positive."""
    chat_id, uid = message.chat.id, message.from_user.id
    cached = _admin_cache.get(chat_id)
    if cached is None or time.monotonic() - cached[1] > _ADMIN_TTL:
        try:
            admins = await message.bot.get_chat_administrators(chat_id)
            cached = ({a.user.id for a in admins}, time.monotonic())
            _admin_cache[chat_id] = cached
        except Exception as e:
            logging.error(f"get_chat_administrators failed: {e}")
            if cached is None:
                return False  # no data — fall back to moderating
    return uid in cached[0]


@router.message((F.chat.type == ChatType.SUPERGROUP) | (F.chat.type == ChatType.GROUP))
async def handle_spam_detection(message: Message) -> None:
    if not groups.is_allowed(message.chat.id):
        return  # cost guard: unauthorized group -> no classification, no Gemini

    # Channel posts / anonymous admins have no from_user; we can't moderate them
    # by user id (and shouldn't moderate admins/channels anyway).
    if message.sender_chat or not message.from_user:
        return

    text = message.text or message.caption or ""
    if not text.strip():
        return

    if await _sender_is_admin(message):
        return  # never moderate group admins

    # First message from this sender? Scan their full profile once (bio + photos).
    # This is the only place link-joiners get profile-checked (their join emitted
    # no new_chat_members event). Nudity / explicit-channel links are
    # hard-banned + deleted here, ahead of any keyword check.
    pkey = (message.chat.id, message.from_user.id)
    if pkey not in _profile_checked:
        if len(_profile_checked) > _PROFILE_CHECK_CAP:
            _profile_checked.clear()
        _profile_checked.add(pkey)
        from .profile_checker import check_profile, is_severe  # lazy: avoids a cycle
        preason = await check_profile(message.bot, message.from_user, message.chat.id)
        if preason:
            await _delete_message_safe(message)
            severe = is_severe(preason)
            await block_user(message.bot, message.chat.id, message.from_user.id, preason,
                             user_type="bot" if severe else "human",
                             is_permanent=severe, ban=severe)
            await notify_admins(message.bot, message, preason, "bot" if severe else "human")
            return  # severe -> banned; soft -> muted pending review

    reason = classify_spam(text, key=(message.chat.id, message.from_user.id),
                           group_id=message.chat.id)
    if not reason:
        # Message looks fine. But if an admin flagged this account as a suspicious
        # bot profile, surface it (never auto-act) — once an hour per chat/user.
        if watchlist.is_watched(message.from_user.id, message.chat.id) and \
                _watch_alert.allow((message.chat.id, message.from_user.id)):
            await notify_admins_watched(message.bot, message)
        return

    await _report_spam(message, reason)
    await _delete_message_safe(message)

    is_bot = is_bot_account(message)
    user_type = "bot" if is_bot else "human"
    await block_user(message.bot, message.chat.id, message.from_user.id,
                     reason, user_type, is_permanent=is_bot)
    if not is_bot:  # humans get a 24h mute (block_user's default) — announce it
        await announce_mute(message.bot, message.chat.id, message.from_user.full_name, 24, reason)
    await notify_admins(message.bot, message, reason, user_type)


def register_spam_handlers(dp) -> None:
    dp.include_router(router)
