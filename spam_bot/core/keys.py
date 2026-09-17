"""Per-group BYOK Gemini key storage (encrypted via core.crypto)."""
import logging
from datetime import datetime

from . import crypto


def set_key(group_id: int, plaintext: str, set_by: int) -> bool:
    enc = crypto.encrypt(plaintext)
    if enc is None:
        return False  # no KEY_ENCRYPTION_SECRET configured
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        row = db.get(GroupConfig, group_id)
        if row:
            row.gemini_key_encrypted = enc
            row.key_set_by = set_by
            row.key_set_at = datetime.utcnow()
        else:
            db.add(GroupConfig(chat_id=group_id, gemini_key_encrypted=enc,
                               key_set_by=set_by, key_set_at=datetime.utcnow()))
        db.commit()
    return True


def get_key(group_id):
    if group_id is None:
        return None
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
        return crypto.decrypt(row.gemini_key_encrypted) if row and row.gemini_key_encrypted else None
    except Exception as e:
        logging.error(f"get_key failed: {e}")
        return None


def has_key(group_id) -> bool:
    return get_key(group_id) is not None


# The operator's shared key. Telegram never issues chat id 0, so this scope can't
# collide with a real group, and the key reuses the same encrypted GroupConfig row
# (with its set_by / set_at columns) and the same /key web form as a group key.
GLOBAL_SCOPE = 0


def get_global_key():
    return get_key(GLOBAL_SCOPE)


def delete_key(group_id) -> bool:
    """Remove a stored key. True if there was one."""
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
            if not row or not row.gemini_key_encrypted:
                return False
            row.gemini_key_encrypted = None
            row.key_set_by = None
            row.key_set_at = None
            db.commit()
        return True
    except Exception as e:
        logging.error(f"delete_key failed: {e}")
        return False


def key_info(group_id):
    """(set_by, set_at) for a stored key, or None. Never returns the key itself."""
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
            if row and row.gemini_key_encrypted:
                return row.key_set_by, row.key_set_at
    except Exception as e:
        logging.error(f"key_info failed: {e}")
    return None


def resolve_key(group_id):
    """(key, source) the AI layer should use for a group: its own key first, then
    the operator's shared key. source is 'own', 'global' or None. A call with no
    group (the operator's private forward-to-check flow) never falls back — it
    stays keyless exactly as it was before the shared key existed."""
    if group_id is None:
        return None, None
    own = get_key(group_id)
    if own:
        return own, "own"
    shared = get_global_key()
    if shared:
        return shared, "global"
    return None, None


def key_source(group_id):
    return resolve_key(group_id)[1]
