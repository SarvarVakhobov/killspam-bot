"""Run: python -m pytest tests/test_linkcheck.py  (no network: VirusTotal is a local fake).

Guards phishing-link blocking: the 2026-09 "ijtimoiy yordam" scam (a link showing
gov.uz that opens another site) is caught without any key; honest links are not;
VirusTotal is budgeted, cached, never sees skipped platforms, and a failure lets
the message through instead of blocking it.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from aiogram.types import MessageEntity
from aiohttp import web
from aiohttp.test_utils import TestServer

from spam_bot.core import linkcheck as lc
from spam_bot.handlers import profile_checker
from spam_bot.handlers import spam_detector as sd

SCAM = (
    "🇺🇿 Sizga qanday ijtimoiy yordam ajratilishi mumkin?\n\n"
    "💰 Dastur doirasida 35 000 000 so'mgacha.\n\n"
    "👉 IJTIMOIY YORDAMNI TEKSHIRISH\n"
    "https://gov.uz/viplata2026"
)


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _entity(text, shown, type_="text_link", url=None):
    """An entity over `shown`, with Telegram's UTF-16 offsets (emoji count double)."""
    i = text.index(shown)
    return MessageEntity(type=type_, offset=_u16(text[:i]), length=_u16(shown), url=url)


@pytest.fixture(autouse=True)
def _vt(monkeypatch):
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "test-key")
    monkeypatch.setattr(lc, "VT_MALICIOUS_THRESHOLD", 2)
    monkeypatch.setattr(lc, "_minute", lc.RateLimiter(limit=100, window=60.0))
    monkeypatch.setattr(lc, "_day", lc.RateLimiter(limit=100, window=86400.0))
    lc._cache.clear()
    yield
    lc._cache.clear()


def _fake_vt(monkeypatch, verdicts):
    """Replace the HTTP call; record which domains were looked up."""
    calls = []

    async def lookup(domain):
        calls.append(domain)
        return verdicts.get(domain, (0, True))
    monkeypatch.setattr(lc, "_vt_lookup", lookup)
    return calls


# --- deceptive links (no key needed) ---------------------------------------------

def test_reported_scam_is_caught_despite_emoji_offsets():
    ents = [_entity(SCAM, "https://gov.uz/viplata2026", url="https://uzbekistan.whitestake.cc/")]
    assert lc.deceptive_link(SCAM, ents) == \
        "deceptive link: shows gov.uz, opens uzbekistan.whitestake.cc"


def test_label_text_is_not_deceptive():
    # "Click here"-style labels are normal; only a *shown address* can lie.
    t = "👉 IJTIMOIY YORDAMNI TEKSHIRISH"
    assert lc.deceptive_link(t, [_entity(t, "IJTIMOIY YORDAMNI TEKSHIRISH", url="https://evil.cc")]) is None


@pytest.mark.parametrize("shown,real", [
    ("https://gov.uz/viplata", "https://my.gov.uz/viplata"),     # subdomain of the shown site
    ("www.kun.uz/news", "https://kun.uz/news/1"),                 # www. and path differ
    ("t.me/python_uz", "https://t.me/python_uz"),
    ("https://GOV.UZ/x", "http://gov.uz/y"),                      # case / scheme
])
def test_same_site_is_not_deceptive(shown, real):
    t = f"Havola: {shown}"
    assert lc.deceptive_link(t, [_entity(t, shown, url=real)]) is None


def test_bare_word_that_looks_like_a_domain_is_ignored():
    t = "readme.md"
    assert lc.deceptive_link(t, [_entity(t, t, url="https://github.com/x/y")]) is None


def test_userinfo_trick_reads_the_real_host():
    t = "https://gov.uz/login"
    assert lc.deceptive_link(t, [_entity(t, t, url="https://gov.uz@evil.cc/login")]) == \
        "deceptive link: shows gov.uz, opens evil.cc"


def test_non_web_links_are_ignored():
    t = "https://gov.uz/app"
    assert lc.deceptive_link(t, [_entity(t, t, url="tg://resolve?domain=gov")]) is None


def test_link_hosts_collects_visible_and_hidden_links_once():
    t = "a kun.uz/x b https://evil.cc/p c https://evil.cc/q d"
    ents = [_entity(t, "kun.uz/x", "url"), _entity(t, "https://evil.cc/p", "url"),
            _entity(t, "c", url="https://www.evil.cc/other")]
    assert lc.link_hosts(t, ents) == ["kun.uz", "evil.cc"]


# --- VirusTotal ------------------------------------------------------------------

def _msg(text, entities, caption=False):
    return SimpleNamespace(
        text=None if caption else text, caption=text if caption else None,
        entities=None if caption else entities, caption_entities=entities if caption else None)


def test_flagged_domain_blocks(monkeypatch):
    calls = _fake_vt(monkeypatch, {"whitestake.cc": (7, True)})
    t = "Yordam: https://uzbekistan.whitestake.cc/form"
    reason = asyncio.run(lc.check_message(_msg(t, [_entity(t, "https://uzbekistan.whitestake.cc/form", "url")])))
    assert reason == "malicious link: VirusTotal flags whitestake.cc (7 engines)"
    assert calls == ["uzbekistan.whitestake.cc", "whitestake.cc"]   # parent checked too


def test_below_threshold_passes(monkeypatch):
    _fake_vt(monkeypatch, {"meh.cc": (1, True)})
    t = "https://meh.cc/x"
    assert asyncio.run(lc.check_message(_msg(t, [_entity(t, t, "url")]))) is None


def test_caption_links_are_checked(monkeypatch):
    _fake_vt(monkeypatch, {"evil.cc": (3, True)})
    t = "rasm tavsifi https://evil.cc"
    assert asyncio.run(lc.check_message(_msg(t, [_entity(t, "https://evil.cc", "url")], caption=True)))


def test_skipped_platforms_never_reach_virustotal(monkeypatch):
    calls = _fake_vt(monkeypatch, {})
    t = "https://t.me/kanal https://www.youtube.com/watch?v=1 https://my.gov.uz/x"
    ents = [_entity(t, s, "url") for s in t.split()]
    assert asyncio.run(lc.check_message(_msg(t, ents))) is None
    assert calls == []


def test_verdicts_are_cached(monkeypatch):
    calls = _fake_vt(monkeypatch, {"evil.cc": (5, True)})
    for _ in range(3):
        assert asyncio.run(lc.malicious_count("evil.cc")) == 5
    assert calls == ["evil.cc"]


def test_failures_are_not_cached_and_let_the_message_pass(monkeypatch):
    calls = []

    async def broken(domain):
        calls.append(domain)
        return None
    monkeypatch.setattr(lc, "_vt_lookup", broken)
    t = "https://evil.cc"
    assert asyncio.run(lc.check_message(_msg(t, [_entity(t, t, "url")]))) is None
    assert asyncio.run(lc.malicious_count("evil.cc")) is None
    assert calls == ["evil.cc", "evil.cc"]


def test_spent_budget_skips_lookup(monkeypatch):
    calls = _fake_vt(monkeypatch, {"evil.cc": (9, True)})
    monkeypatch.setattr(lc, "_minute", lc.RateLimiter(limit=0, window=60.0))
    assert asyncio.run(lc.malicious_count("evil.cc")) is None
    assert calls == []


def test_no_key_means_no_lookups_but_deception_still_caught(monkeypatch):
    calls = _fake_vt(monkeypatch, {"evil.cc": (9, True)})
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    t = "https://evil.cc"
    assert asyncio.run(lc.check_message(_msg(t, [_entity(t, t, "url")]))) is None
    ents = [_entity(SCAM, "https://gov.uz/viplata2026", url="https://evil.cc/")]
    assert asyncio.run(lc.check_message(_msg(SCAM, ents))).startswith("deceptive link")
    assert calls == []


def test_http_parsing_against_a_local_fake(monkeypatch):
    seen_keys = []

    async def domains(request):
        seen_keys.append(request.headers.get("x-apikey"))
        d = request.match_info["d"]
        if d == "evil.cc":
            return web.json_response({"data": {"attributes": {"last_analysis_stats": {
                "malicious": 6, "suspicious": 1, "harmless": 50, "undetected": 20}}}})
        if d == "new.cc":
            return web.json_response({"error": {"code": "NotFoundError"}}, status=404)
        return web.json_response({"error": {"code": "WrongCredentialsError"}}, status=401)

    async def run():
        app = web.Application()
        app.router.add_get("/api/v3/domains/{d}", domains)
        server = TestServer(app)
        await server.start_server()
        try:
            monkeypatch.setattr(lc, "_VT_DOMAIN_URL",
                                f"http://{server.host}:{server.port}/api/v3/domains/{{}}")
            return (await lc._vt_lookup("evil.cc"), await lc._vt_lookup("new.cc"),
                    await lc._vt_lookup("badkey.cc"))
        finally:
            await server.close()

    assert asyncio.run(run()) == ((6, True), (0, False), None)
    assert seen_keys == ["test-key"] * 3


# --- handler ---------------------------------------------------------------------

def test_group_handler_deletes_and_mutes_without_calling_ai(monkeypatch):
    deleted, blocked, alerts = [], {}, []

    class Bot:
        async def delete_message(self, chat_id, message_id):
            deleted.append(message_id)

    async def no(*a, **k):
        return False

    async def nothing(*a, **k):
        return None

    async def block(bot, chat_id, user_id, reason, user_type, is_permanent=False, ban=False):
        blocked.update(reason=reason, user_type=user_type, permanent=is_permanent, ban=ban)

    async def alert(bot, message, reason, user_type):
        alerts.append(reason)

    def ai_must_not_run(*a, **k):
        raise AssertionError("a phishing post must not cost a Gemini call")

    ents = [_entity(SCAM, "https://gov.uz/viplata2026", url="https://uzbekistan.whitestake.cc/")]
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup", title="T"),
        from_user=SimpleNamespace(id=5, full_name="U", username="u", is_bot=False),
        sender_chat=None, message_id=77, text=SCAM, caption=None,
        entities=ents, caption_entities=None, bot=Bot())
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    monkeypatch.setattr(sd.groups, "is_allowed", lambda cid: True)
    monkeypatch.setattr(sd, "_sender_is_admin", no)
    monkeypatch.setattr(profile_checker, "check_profile", nothing)
    monkeypatch.setattr(sd, "_report_spam", nothing)
    monkeypatch.setattr(sd, "announce_mute", nothing)
    monkeypatch.setattr(sd, "block_user", block)
    monkeypatch.setattr(sd, "notify_admins", alert)
    monkeypatch.setattr(sd, "classify_spam", ai_must_not_run)
    sd._profile_checked.clear()

    asyncio.run(sd.handle_spam_detection(msg))

    assert deleted == [77]
    assert blocked == {"reason": "deceptive link: shows gov.uz, opens uzbekistan.whitestake.cc",
                       "user_type": "human", "permanent": False, "ban": False}   # 24h mute, undoable
    assert alerts == [blocked["reason"]]
