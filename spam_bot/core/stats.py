"""Operator-facing bot stats: which groups use the bot and how much spam each is
catching. Read-only aggregation over AllowedGroup / SpamReport / BlockedUser.

Complements usage.py, which tracks Gemini token *cost*; this tracks *activity*.
Group titles aren't stored (only chat_id is), so callers with a bot resolve them
via resolve_titles() and pass the map into report().
"""
import logging

from . import usage


def _grouped_count(model, ts_col, start_utc, end_utc) -> dict:
    """{group_id: row count} for `model` in [start, end). Best-effort."""
    from sqlalchemy import func
    from ..db.session import SessionLocal
    try:
        with SessionLocal() as db:
            rows = (db.query(model.group_id, func.count(model.id))
                    .filter(ts_col >= start_utc, ts_col < end_utc)
                    .group_by(model.group_id).all())
        return {gid: int(c) for gid, c in rows}
    except Exception as e:
        logging.error(f"stats._grouped_count failed: {e}")
        return {}


def spam_counts(start_utc, end_utc) -> dict:
    from ..db.models import SpamReport
    return _grouped_count(SpamReport, SpamReport.reported_at, start_utc, end_utc)


def ban_counts(start_utc, end_utc) -> dict:
    from ..db.models import BlockedUser
    return _grouped_count(BlockedUser, BlockedUser.blocked_at, start_utc, end_utc)


def group_inventory() -> list:
    """Every protected group: (chat_id, enabled_at, ai_on). ai_on = the AI layer
    actually runs for it: switched on (/ai) and a key resolves — its own or the
    operator's shared key."""
    from ..db.session import SessionLocal
    from ..db.models import AllowedGroup
    from . import ai_settings, keys
    try:
        with SessionLocal() as db:
            rows = db.query(AllowedGroup).all()
            groups = [(g.chat_id, g.enabled_at) for g in rows]
        return [(cid, at, ai_settings.is_enabled(cid) and keys.key_source(cid) is not None)
                for cid, at in groups]
    except Exception as e:
        logging.error(f"stats.group_inventory failed: {e}")
        return []


def _label(chat_id, titles: dict) -> str:
    t = titles.get(chat_id)
    return f"{t} ({chat_id})" if t else str(chat_id)


def report(titles: dict = None) -> str:
    """Operator stats DM: group roster + spam/ban activity per window."""
    from . import ai_settings, keys
    titles = titles or {}
    inv = group_inventory()

    lines = [f"🤖 Bot stats — {len(inv)} group(s) protected"]

    if inv:
        lines.append("\nGroups:")
        for cid, at, ai_on in sorted(inv, key=lambda r: (r[1] or usage.datetime.min)):
            since = at.strftime("%Y-%m-%d") if at else "?"
            if ai_on:
                ai = "on" if keys.has_key(cid) else "on (shared key)"
            elif not ai_settings.is_enabled(cid):
                ai = "off (switched off)"
            else:
                ai = "off (no key)"
            lines.append(f"  • {_label(cid, titles)} — since {since}, AI: {ai}")

    windows = [
        ("Yesterday", usage.yesterday_bounds_utc(), True),
        ("Last 7 days", usage.rolling_bounds_utc(7), False),
        ("Last 30 days", usage.rolling_bounds_utc(30), False),
    ]
    for label, (start, end), breakdown in windows:
        spam = spam_counts(start, end)
        bans = ban_counts(start, end)
        lines.append(f"\n📊 {label}: {sum(spam.values())} spam removed, "
                     f"{sum(bans.values())} banned")
        if breakdown:
            for cid in sorted(set(spam) | set(bans), key=lambda c: -spam.get(c, 0)):
                lines.append(f"    • {_label(cid, titles)} — "
                             f"{spam.get(cid, 0)} spam, {bans.get(cid, 0)} banned")
    return "\n".join(lines)


async def resolve_titles(bot, chat_ids) -> dict:
    """{chat_id: title} via get_chat, best-effort (skips ones that error)."""
    titles = {}
    for cid in chat_ids:
        try:
            titles[cid] = (await bot.get_chat(cid)).title or str(cid)
        except Exception as e:
            logging.info(f"stats: couldn't resolve title for {cid}: {e}")
    return titles
