"""Operator switch for the paid AI layer (/ai): one default for every group plus
per-group overrides, so the operator decides where Gemini runs — and who pays.

Stored on GroupConfig.ai_enabled. A group row's value forces AI on/off for that
group; NULL follows the default. The default lives on the keys.GLOBAL_SCOPE row,
where NULL means on — so a deploy that never touches /ai behaves exactly as
before. Switching AI on can't conjure a key: a group still needs its own key or
the operator's shared one (/globalkey) for the AI to actually run."""
import logging

from . import keys


def _read(chat_id):
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        row = db.get(GroupConfig, chat_id)
        return row.ai_enabled if row else None


def _write(chat_id, value) -> None:
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        row = db.get(GroupConfig, chat_id)
        if row is None:
            if value is None:
                return  # nothing stored, nothing to clear
            row = GroupConfig(chat_id=chat_id)
            db.add(row)
        row.ai_enabled = value
        db.commit()


def default_enabled() -> bool:
    try:
        value = _read(keys.GLOBAL_SCOPE)
    except Exception as e:
        logging.error(f"ai_settings.default_enabled failed: {e}")
        return False
    return True if value is None else bool(value)


def is_enabled(chat_id) -> bool:
    """Should the AI layer run for this group? Fails closed (off) on a DB error —
    the key lookup would fail then too, and off is the cheap direction."""
    try:
        value = _read(chat_id)
    except Exception as e:
        logging.error(f"ai_settings.is_enabled failed for {chat_id}: {e}")
        return False
    return default_enabled() if value is None else bool(value)


def set_group(chat_id, enabled: bool) -> None:
    """Force AI on/off for one group. A value equal to the default is stored as
    "follow the default", so a later set_all still reaches this group."""
    _write(chat_id, None if enabled == default_enabled() else enabled)


def set_all(enabled: bool) -> None:
    """Set the default for every group, current and future, and drop every
    per-group override — so the switch really means all of them."""
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        db.query(GroupConfig).filter(GroupConfig.chat_id != keys.GLOBAL_SCOPE) \
            .update({GroupConfig.ai_enabled: None})
        db.commit()
    _write(keys.GLOBAL_SCOPE, enabled)


def status(chat_id) -> str:
    """'off' (switched off) | 'nokey' (on, but no key resolves) | 'own' | 'global'."""
    if not is_enabled(chat_id):
        return "off"
    return keys.key_source(chat_id) or "nokey"
