"""Single-use, short-TTL grants for the key-entry web form.

Only a SHA-256 hash of each token is stored, so a DB-only leak can't be replayed
(combined with single-use + 15-min TTL). The raw token lives only in the link
we DM the admin and in the form round-trip.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta

_TTL_MIN = 15


def _hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def mint(chat_id: int, created_by: int, kind: str = "gemini") -> str | None:
    from ..db.session import SessionLocal
    from ..db.models import TokenGrant
    tok = secrets.token_urlsafe(32)
    try:
        with SessionLocal() as db:
            db.add(TokenGrant(token=_hash(tok), chat_id=chat_id, created_by=created_by,
                              kind=kind,
                              expires_at=datetime.utcnow() + timedelta(minutes=_TTL_MIN)))
            db.commit()
        return tok  # raw token to the caller; only its hash is persisted
    except Exception as e:
        logging.error(f"token mint failed: {e}")
        return None


def validate(tok: str):
    """Return a plain dict with grant fields if usable, else None. The returned
    'token' is the RAW token (so the form can round-trip it), not the stored hash."""
    from ..db.session import SessionLocal
    from ..db.models import TokenGrant
    if not tok:
        return None
    with SessionLocal() as db:
        row = db.get(TokenGrant, _hash(tok))
        if not row or row.used or (row.expires_at and row.expires_at < datetime.utcnow()):
            return None
        return {"token": tok, "chat_id": row.chat_id, "created_by": row.created_by,
                "kind": row.kind or "gemini"}   # NULL: a grant minted before kinds existed


def consume(tok: str) -> None:
    from ..db.session import SessionLocal
    from ..db.models import TokenGrant
    with SessionLocal() as db:
        row = db.get(TokenGrant, _hash(tok))
        if row:
            row.used = True
            db.commit()
