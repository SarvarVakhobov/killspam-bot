"""Encrypted API-key storage (via core.crypto): each group's own keys plus the
operator's shared ones.

Two kinds of key live side by side on a GroupConfig row: "gemini" for AI
moderation (/setkey) and "vt" for VirusTotal link checks (/setvtkey). Every
function takes kind= and defaults to "gemini", the original one.
"""
import logging
from datetime import datetime

from . import crypto

# kind -> (encrypted-key column, set-by column, set-at column) on GroupConfig
_COLUMNS = {
    "gemini": ("gemini_key_encrypted", "key_set_by", "key_set_at"),
    "vt": ("vt_key_encrypted", "vt_key_set_by", "vt_key_set_at"),
}

# The operator's shared keys. Telegram never issues chat id 0, so this scope can't
# collide with a real group, and a shared key reuses the same encrypted row and the
# same /key web form as a group key.
GLOBAL_SCOPE = 0


def _cols(kind):
    try:
        return _COLUMNS[kind]
    except KeyError:
        raise ValueError(f"unknown key kind: {kind!r}") from None


def set_key(group_id: int, plaintext: str, set_by: int, kind: str = "gemini") -> bool:
    key_col, by_col, at_col = _cols(kind)
    enc = crypto.encrypt(plaintext)
    if enc is None:
        return False  # no KEY_ENCRYPTION_SECRET configured
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        row = db.get(GroupConfig, group_id)
        if row is None:
            row = GroupConfig(chat_id=group_id)
            db.add(row)
        setattr(row, key_col, enc)
        setattr(row, by_col, set_by)
        setattr(row, at_col, datetime.utcnow())
        db.commit()
    return True


def get_key(group_id, kind: str = "gemini"):
    key_col = _cols(kind)[0]
    if group_id is None:
        return None
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
            enc = getattr(row, key_col) if row else None
        return crypto.decrypt(enc) if enc else None
    except Exception as e:
        logging.error(f"get_key failed: {e}")
        return None


def has_key(group_id, kind: str = "gemini") -> bool:
    return get_key(group_id, kind) is not None


def get_global_key(kind: str = "gemini"):
    return get_key(GLOBAL_SCOPE, kind)


def delete_key(group_id, kind: str = "gemini") -> bool:
    """Remove a stored key. True if there was one."""
    key_col, by_col, at_col = _cols(kind)
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
            if not row or not getattr(row, key_col):
                return False
            for col in (key_col, by_col, at_col):
                setattr(row, col, None)
            db.commit()
        return True
    except Exception as e:
        logging.error(f"delete_key failed: {e}")
        return False


def key_info(group_id, kind: str = "gemini"):
    """(set_by, set_at) for a stored key, or None. Never returns the key itself."""
    key_col, by_col, at_col = _cols(kind)
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
            if row and getattr(row, key_col):
                return getattr(row, by_col), getattr(row, at_col)
    except Exception as e:
        logging.error(f"key_info failed: {e}")
    return None


def resolve_key(group_id, kind: str = "gemini"):
    """(key, source) to use for a group: its own key first, then the operator's
    shared key. source is 'own', 'global' or None. A call with no group (the
    operator's private forward-to-check flow) never falls back."""
    if group_id is None:
        return None, None
    own = get_key(group_id, kind)
    if own:
        return own, "own"
    shared = get_global_key(kind)
    if shared:
        return shared, "global"
    return None, None


def key_source(group_id, kind: str = "gemini"):
    return resolve_key(group_id, kind)[1]
