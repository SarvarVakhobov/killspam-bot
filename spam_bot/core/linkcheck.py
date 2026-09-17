"""Link checks for group messages: phishing links and app downloads.

Cheapest first:

1. App downloads (free). An attached .apk/.exe file, or a link to one — the
   usual way to hand someone an account-stealing "app".
2. Deceptive link (free, no network). Telegram lets a message show one text and
   open another address (a "text_link"). When the shown text is itself a web
   address but the link opens a different site — "https://gov.uz/viplata2026"
   that really goes to uzbekistan.whitestake.cc — it is disguised on purpose.
3. VirusTotal domain reputation. The real host of each link is looked up with the
   group's own key (/setvtkey), else the operator's shared key (/globalvtkey),
   else the server's VIRUSTOTAL_API_KEY. Only the domain is sent, never the message.

The public VirusTotal API allows 4 lookups a minute and 500 a day *per key*, so
each key gets its own budget. Verdicts are cached (a domain's reputation doesn't
depend on whose key asked), big platforms are never looked up, and a spent budget
or a failed lookup lets the message through rather than holding moderation up.
"""
import hashlib
import logging
import re
import time
from urllib.parse import urlsplit

from . import keys
from .config import VIRUSTOTAL_API_KEY, VT_MALICIOUS_THRESHOLD
from .patterns import APP_EXTENSIONS
from .ratelimit import RateLimiter

_VT_DOMAIN_URL = "https://www.virustotal.com/api/v3/domains/{}"
_VT_TIMEOUT = 6.0
_KNOWN_TTL = 6 * 3600     # VirusTotal has a verdict: good for hours
_UNKNOWN_TTL = 3600       # never scanned yet: ask again sooner, new phishing sites get scanned
_CACHE_CAP = 5000
_MAX_HOSTS = 3            # links looked up per message
_MINUTE_LIMIT, _DAY_LIMIT = 4, 500   # VirusTotal public-API quota, per key

_budgets: dict = {}       # sha256(key)[:16] -> (per-minute limiter, per-day limiter)
_cache: dict = {}         # domain -> (malicious_count, expires_at monotonic)

# Platforms whose *domain* VirusTotal always rates clean, even when one page on
# them is bad — looking them up only burns the daily budget.
_SKIP_HOSTS = (
    "t.me", "telegram.me", "telegram.org", "telegra.ph",
    "google.com", "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "x.com", "twitter.com", "tiktok.com",
    "github.com", "wikipedia.org", "gov.uz",
)

# Shown text that reads as a web address: a scheme, "www.", or domain/path.
# A bare "readme.md" is left alone — too many ordinary words look like domains.
_LOOKS_LIKE_URL = re.compile(
    r"^(?:https?://\S+|www\.\S+|(?:[\w-]+\.)+[^\W\d_]{2,}/\S*)$", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def _split(address: str):
    """urlsplit() of an address, assuming http:// when it has no scheme."""
    a = (address or "").strip()
    if not _SCHEME.match(a):
        a = "http://" + a
    return urlsplit(a)


def _web_host(address: str):
    """Lower-case host of an http(s) address, without "www." — or None for any
    other scheme (tg://, mailto:) or something that isn't an address at all."""
    try:
        parts = _split(address)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host or "." not in host:
        return None
    host = host.rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return host[4:] if host.startswith("www.") else host


def _same_site(a: str, b: str) -> bool:
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _links(text: str, entities):
    """(entity, address) for every web link in a message, visible or hidden."""
    for e in entities or ():
        if e.type == "url":
            yield e, e.extract_from(text or "")
        elif e.type == "text_link" and e.url:
            yield e, e.url


def deceptive_link(text: str, entities):
    """A hidden link whose shown text is a web address of a different site."""
    for e, address in _links(text, entities):
        if e.type != "text_link":
            continue
        shown = e.extract_from(text or "").strip()
        if not _LOOKS_LIKE_URL.match(shown):
            continue
        shown_host, real_host = _web_host(shown), _web_host(address)
        if shown_host and real_host and not _same_site(shown_host, real_host):
            return f"deceptive link: shows {shown_host}, opens {real_host}"
    return None


def app_link(text: str, entities):
    """A link (visible or hidden) whose path ends in an app/program file. A bare
    file name with no link ("run python.exe") is ordinary tech talk and passes."""
    for _e, address in _links(text, entities):
        if not _web_host(address):
            continue
        try:
            path = _split(address).path
        except ValueError:
            continue
        if path.lower().endswith(APP_EXTENSIONS):
            return f"app download link: {path.rsplit('/', 1)[-1]}"
    return None


def app_file(message):
    """An attached app/program file (.apk/.exe/...)."""
    document = getattr(message, "document", None)
    name = (getattr(document, "file_name", None) or "") if document else ""
    if name.lower().endswith(APP_EXTENSIONS):
        return f"app file attached: {name}"
    return None


def link_hosts(text: str, entities) -> list:
    """Real hosts of every link in a message, in order, without duplicates."""
    hosts = []
    for _e, address in _links(text, entities):
        host = _web_host(address)
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _skipped(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _SKIP_HOSTS)


def _candidates(host: str) -> list:
    """The host, plus its parent domain: phishing kits run on per-campaign
    subdomains (uzbekistan.whitestake.cc) that VirusTotal may not have scanned
    while the parent domain is already flagged."""
    labels = host.split(".")
    return [host] if len(labels) <= 2 else [host, ".".join(labels[-2:])]


def vt_key_for(group_id):
    """The VirusTotal key a group's link checks use: its own, else the operator's
    shared key, else the server's .env key. None = no VirusTotal lookups."""
    return keys.resolve_key(group_id, "vt")[0] or VIRUSTOTAL_API_KEY or None


def _budget(api_key: str):
    h = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    b = _budgets.get(h)
    if b is None:
        b = _budgets[h] = (RateLimiter(limit=_MINUTE_LIMIT, window=60.0),
                           RateLimiter(limit=_DAY_LIMIT, window=86400.0))
    return b


async def _vt_get(domain: str, api_key: str):
    """(status, json-or-None) of a VirusTotal domain lookup. Raises on network errors."""
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=_VT_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(_VT_DOMAIN_URL.format(domain),
                               headers={"x-apikey": api_key}) as resp:
            return resp.status, (await resp.json() if resp.status == 200 else None)


async def _vt_lookup(domain: str, api_key: str):
    """(malicious_engines, known) for a domain, or None when the lookup failed.
    known=False means VirusTotal has never seen the domain."""
    try:
        status, data = await _vt_get(domain, api_key)
        if status == 404:
            return 0, False
        if status != 200:
            logging.warning(f"VirusTotal lookup for {domain}: HTTP {status}")
            return None
        stats = data["data"]["attributes"]["last_analysis_stats"]
        return int(stats.get("malicious", 0)), True
    except Exception as e:
        # Type only: an aiohttp error can carry the request, headers included.
        logging.warning(f"VirusTotal lookup for {domain} failed: {type(e).__name__}")
        return None


async def key_works(api_key: str) -> bool:
    """A live lookup of a well-known domain confirms a VirusTotal key before it is
    stored. Fails closed."""
    try:
        status, _data = await _vt_get("google.com", api_key)
        return status == 200
    except Exception as e:
        logging.info(f"VirusTotal key validation failed: {type(e).__name__}")
        return False


async def malicious_count(domain: str, api_key: str):
    """Cached, budgeted VirusTotal verdict: malicious-engine count, or None when
    there is no key, the key's budget is spent, or the lookup failed."""
    if not api_key:
        return None
    now = time.monotonic()
    hit = _cache.get(domain)
    if hit and hit[1] > now:
        return hit[0]
    minute, day = _budget(api_key)
    if not minute.allow("vt") or not day.allow("vt"):
        logging.info(f"VirusTotal budget spent — {domain} not checked")
        return None
    result = await _vt_lookup(domain, api_key)
    if result is None:
        return None             # don't cache a failure; the next link retries
    count, known = result
    if len(_cache) > _CACHE_CAP:
        _cache.clear()
    _cache[domain] = (count, now + (_KNOWN_TTL if known else _UNKNOWN_TTL))
    return count


_SEVERE_PREFIX = "malicious link: VirusTotal flags"


def is_severe(reason) -> bool:
    """A domain VirusTotal engines flag is a confirmed threat -> ban + delete. The
    free checks (disguised link, app download) stay a 24h mute: they are strong
    hints, but a real member can trip them."""
    return bool(reason) and reason.startswith(_SEVERE_PREFIX)


async def check_message(message):
    """Reason string when a group message carries an app download or a phishing
    link, else None."""
    text = message.text or message.caption or ""
    entities = message.entities if message.text else message.caption_entities
    reason = app_file(message) or deceptive_link(text, entities) or app_link(text, entities)
    if reason:
        return reason
    chat = getattr(message, "chat", None)
    api_key = vt_key_for(getattr(chat, "id", None))
    if not api_key:
        return None
    hosts = [h for h in link_hosts(text, entities) if not _skipped(h)]
    for host in hosts[:_MAX_HOSTS]:
        for domain in _candidates(host):
            count = await malicious_count(domain, api_key)
            if count is not None and count >= VT_MALICIOUS_THRESHOLD:
                return f"{_SEVERE_PREFIX} {domain} ({count} engines)"
    return None
