"""Spam matching: regex seed file (git-versioned) + DB-stored learned keywords.

Seed = full regex, hand-edited in patterns/seed_patterns.txt.
Learned = normalized keyword/substring, taught by admins at runtime.
"""
import re
import logging
from pathlib import Path

_SEED_FILE = Path(__file__).resolve().parents[2] / "patterns" / "seed_patterns.txt"

# Cyrillic glyphs that look like Latin letters, used to dodge keyword filters.
# ponytail: covers the common lookalikes; extend the map if new ones turn up.
_HOMOGLYPHS = str.maketrans({
    'а': 'a', 'в': 'b', 'е': 'e', 'к': 'k', 'м': 'm', 'н': 'h', 'о': 'o',
    'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'і': 'i', 'ј': 'j',
})

_URL_RE = re.compile(r'(?:https?://|t\.me/|@)\S+')

# App and program files: a link to one in a *bio* ("yuklab oling: app.apk") is a
# classic account-stealing lure. It mutes for 24h rather than bans — a real member
# can link a genuine installer too. Plain links, t.me channels and @handles are
# deliberately NOT matched.
APP_EXTENSIONS = (".apk", ".xapk", ".apks", ".exe", ".msi", ".dmg", ".bat", ".scr")
_BIO_MALWARE_RE = re.compile(r'\b[\w-]+\.(?:apk|xapk|apks|exe|msi|dmg|bat|scr)\b', re.IGNORECASE)


def has_malware_link(text: str) -> bool:
    """True if a bio names an app/program file (APK/EXE/...)."""
    return bool(text) and bool(_BIO_MALWARE_RE.search(text))


# Any link or handle (incl. bare domains like onlyfans.com). Used only paired with
# the adult check below, so a benign "node.js" or "t.me/python_uz" never blocks alone.
_LINK_RE = re.compile(r'https?://|t\.me/|@\w{3,}|\b[\w-]+\.[a-z]{2,}(?:/|\b)', re.IGNORECASE)

# Explicit/adult terms, bilingual (UZ/RU/EN) + 🔞. ponytail: substring match on strong
# tokens (porn/xxx/onlyfans); extend if spammers obfuscate (Cyrillic look-alikes etc.).
_ADULT_RE = re.compile(
    r'🔞|18\+|onlyfans|porn|xxx|sexy|\bsex\b|\bnudes?\b|escort|camgirl|milf|hookup'
    r'|intim|seks|erotik|yalang|shahvoniy'
    r'|порн|секс|эротик|интим|голы[ехй]|шлюх|простит',
    re.IGNORECASE,
)


def has_explicit_link(text: str) -> bool:
    """True if text has a link/handle AND explicit/adult terms — a bio pushing
    porn/escort/'hot' content behind a t.me or web link. Both must be present, so
    a clean channel link or a link-less message won't trip it."""
    return bool(text) and bool(_ADULT_RE.search(text)) and bool(_LINK_RE.search(text))


def has_link(text: str) -> bool:
    """True if text contains a link, a bare domain or an @handle."""
    return bool(text) and bool(_LINK_RE.search(text))

_seed: dict = {}      # category -> [compiled regex]
_learned: dict = {}   # group_id_or_None -> {category: [normalized keyword]}


def normalize(text: str) -> str:
    return (text or "").lower().translate(_HOMOGLYPHS)


def _load_seed() -> dict:
    cats, cur = {}, None
    for line in _SEED_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1]
            cats[cur] = []
        elif cur:
            cats[cur].append(re.compile(s, re.IGNORECASE | re.UNICODE))
    return cats


def _load_learned() -> dict:
    cats: dict = {}
    try:
        from ..db.session import SessionLocal
        from ..db.models import LearnedPattern
        with SessionLocal() as db:
            for row in db.query(LearnedPattern).all():
                cats.setdefault(row.group_id, {}).setdefault(row.category, []).append(
                    normalize(row.pattern))
    except Exception as e:
        logging.error(f"Failed to load learned patterns: {e}")
    return cats


def reload() -> None:
    """Re-read seed file + learned patterns. Call at startup and after teaching."""
    global _seed, _learned
    _seed = _load_seed()
    _learned = _load_learned()


def _match(category: str, text: str, group_id=None) -> bool:
    for rx in _seed.get(category, []):
        if rx.search(text):
            return True
    norm = normalize(text)
    for gid in (None, group_id):
        if any(kw in norm for kw in _learned.get(gid, {}).get(category, [])):
            return True
    return False


def classify(text: str, group_id=None) -> str | None:
    """Return 'advertisement' | 'inappropriate' | None."""
    if not text:
        return None
    if _match("ads", text, group_id):
        return "advertisement"
    if _match("inappropriate", text, group_id):
        return "inappropriate"
    return None


def is_flirting(text: str, group_id=None) -> bool:
    return bool(text) and _match("flirting", text, group_id)


def extract_keywords(text: str, limit: int = 12) -> list:
    """Candidate keywords/URLs from a spam message, for admin-taught patterns."""
    out = []
    for tok in _URL_RE.findall(text or "") + re.findall(r'\w{4,}', normalize(text)):
        if tok not in out:
            out.append(tok)
    return out[:limit]


def add_learned(patterns: list, category: str, added_by: int, group_id=None) -> int:
    from ..db.session import SessionLocal
    from ..db.models import LearnedPattern
    with SessionLocal() as db:
        for p in patterns:
            db.add(LearnedPattern(pattern=p, category=category, added_by=added_by,
                                  group_id=group_id))
        db.commit()
    reload()
    return len(patterns)


_seed = _load_seed()  # seed needs no DB, load on import; reload() adds learned
