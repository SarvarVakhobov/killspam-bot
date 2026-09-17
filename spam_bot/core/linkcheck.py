"""Phishing-link checks for group messages.

Two signals, cheapest first:

1. Deceptive link (free, no network). Telegram lets a message show one text and
   open another address (a "text_link"). When the shown text is itself a web
   address but the link opens a different site — "https://gov.uz/viplata2026"
   that really goes to uzbekistan.whitestake.cc — it is disguised on purpose; a
   real member linking a site has no reason to dress it up as another one.
2. VirusTotal domain reputation (needs VIRUSTOTAL_API_KEY). The real host of each
   link is looked up; only the domain is sent, never the message.

The public VirusTotal API allows 4 lookups a minute and 500 a day. Results are
cached, big platforms are never looked up, and once the budget is spent the
lookup is skipped and the message passes, rather than holding moderation up.
"""
import logging
import re
import time
from urllib.parse import urlsplit

from .config import VIRUSTOTAL_API_KEY, VT_MALICIOUS_THRESHOLD
from .ratelimit import RateLimiter

_VT_DOMAIN_URL = "https://www.virustotal.com/api/v3/domains/{}"
_VT_TIMEOUT = 6.0
_KNOWN_TTL = 6 * 3600     # VirusTotal has a verdict: good for hours
_UNKNOWN_TTL = 3600       # never scanned yet: ask again sooner, new phishing sites get scanned
_CACHE_CAP = 5000
_MAX_HOSTS = 3            # links looked up per message

_minute = RateLimiter(limit=4, window=60.0)
_day = RateLimiter(limit=500, window=86400.0)
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


def _web_host(address: str):
    """Lower-case host of an http(s) address, without "www." — or None for any
    other scheme (tg://, mailto:) or something that isn't an address at all."""
    a = (address or "").strip()
    if not _SCHEME.match(a):
        a = "http://" + a
    try:
        parts = urlsplit(a)
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


def deceptive_link(text: str, entities):
    """A hidden link whose shown text is a web address of a different site."""
    for e in entities or ():
        if e.type != "text_link" or not e.url:
            continue
        shown = e.extract_from(text or "").strip()
        if not _LOOKS_LIKE_URL.match(shown):
            continue
        shown_host, real_host = _web_host(shown), _web_host(e.url)
        if shown_host and real_host and not _same_site(shown_host, real_host):
            return f"deceptive link: shows {shown_host}, opens {real_host}"
    return None


def link_hosts(text: str, entities) -> list:
    """Real hosts of every link in a message, in order, without duplicates."""
    hosts = []
    for e in entities or ():
        if e.type == "url":
            host = _web_host(e.extract_from(text or ""))
        elif e.type == "text_link":
            host = _web_host(e.url)
        else:
            continue
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


async def _vt_lookup(domain: str):
    """(malicious_engines, known) for a domain, or None when the lookup failed.
    known=False means VirusTotal has never seen the domain."""
    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=_VT_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_VT_DOMAIN_URL.format(domain),
                                   headers={"x-apikey": VIRUSTOTAL_API_KEY}) as resp:
                if resp.status == 404:
                    return 0, False
                if resp.status != 200:
                    logging.warning(f"VirusTotal lookup for {domain}: HTTP {resp.status}")
                    return None
                data = await resp.json()
        stats = data["data"]["attributes"]["last_analysis_stats"]
        return int(stats.get("malicious", 0)), True
    except Exception as e:
        # Type only: an aiohttp error can carry the request, headers included.
        logging.warning(f"VirusTotal lookup for {domain} failed: {type(e).__name__}")
        return None


async def malicious_count(domain: str):
    """Cached, budgeted VirusTotal verdict: malicious-engine count, or None when
    there is no key, no budget left, or the lookup failed."""
    if not VIRUSTOTAL_API_KEY:
        return None
    now = time.monotonic()
    hit = _cache.get(domain)
    if hit and hit[1] > now:
        return hit[0]
    if not _minute.allow("vt") or not _day.allow("vt"):
        logging.info(f"VirusTotal budget spent — {domain} not checked")
        return None
    result = await _vt_lookup(domain)
    if result is None:
        return None             # don't cache a failure; the next link retries
    count, known = result
    if len(_cache) > _CACHE_CAP:
        _cache.clear()
    _cache[domain] = (count, now + (_KNOWN_TTL if known else _UNKNOWN_TTL))
    return count


async def check_message(message):
    """Reason string when a group message carries a phishing link, else None."""
    text = message.text or message.caption or ""
    entities = message.entities if message.text else message.caption_entities
    reason = deceptive_link(text, entities)
    if reason or not VIRUSTOTAL_API_KEY:
        return reason
    hosts = [h for h in link_hosts(text, entities) if not _skipped(h)]
    for host in hosts[:_MAX_HOSTS]:
        for domain in _candidates(host):
            count = await malicious_count(domain)
            if count is not None and count >= VT_MALICIOUS_THRESHOLD:
                return f"malicious link: VirusTotal flags {domain} ({count} engines)"
    return None
