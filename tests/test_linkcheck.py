"""Run: python -m pytest tests/test_linkcheck.py  (no network: VirusTotal is a local fake).

Guards the link checks: the 2026-09 "ijtimoiy yordam" scam (a link showing gov.uz
that opens another site) and app downloads are caught without any key; honest
links and tech talk are not; a VirusTotal-confirmed link bans while the free
checks only mute; VirusTotal is budgeted per key, cached, never sees skipped
platforms, and a failure lets the message through instead of blocking it.
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


def _msg(text, entities=None, caption=False, document=None, chat_id=None):
    return SimpleNamespace(
        text=None if caption else text, caption=text if caption else None,
        entities=None if caption else entities, caption_entities=entities if caption else None,
        document=document, chat=SimpleNamespace(id=chat_id) if chat_id else None)


@pytest.fixture(autouse=True)
def _vt(monkeypatch):
    # No group keys in play: vt_key_for() falls through to the server .env key.
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "test-key")
    monkeypatch.setattr(lc, "VT_MALICIOUS_THRESHOLD", 2)
    monkeypatch.setattr(lc, "_MINUTE_LIMIT", 100)
    monkeypatch.setattr(lc, "_DAY_LIMIT", 100)
    lc._budgets.clear()
    lc._cache.clear()
    yield
    lc._budgets.clear()
    lc._cache.clear()


def _fake_vt(monkeypatch, verdicts):
    """Replace the HTTP call; record (domain, key) of every lookup."""
    calls = []

    async def lookup(domain, api_key):
        calls.append((domain, api_key))
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


# --- app downloads (no key needed) -----------------------------------------------

def test_visible_app_link_is_caught():
    t = "Yangi versiya: https://x.site/files/Click.apk?v=2"
    assert lc.app_link(t, [_entity(t, "https://x.site/files/Click.apk?v=2", "url")]) == \
        "app download link: Click.apk"


def test_hidden_app_link_is_caught():
    t = "👉 YANGILASH"
    assert lc.app_link(t, [_entity(t, "YANGILASH", url="https://evil.cc/update.EXE")]) == \
        "app download link: update.EXE"


def test_file_name_without_a_link_is_tech_talk():
    # "run python.exe" in an IT group is not a download.
    assert asyncio.run(lc.check_message(_msg("python.exe ni ishga tushiring, keyin app.apk"))) is None


def test_attached_app_file_is_caught():
    doc = SimpleNamespace(file_name="Click_yangi.apk")
    assert lc.app_file(_msg(None, document=doc)) == "app file attached: Click_yangi.apk"


def test_ordinary_document_passes():
    assert lc.app_file(_msg(None, document=SimpleNamespace(file_name="kurs.pdf"))) is None
    assert lc.app_file(_msg(None, document=SimpleNamespace(file_name=None))) is None


def test_only_virustotal_verdicts_are_severe():
    assert lc.is_severe("malicious link: VirusTotal flags evil.cc (7 engines)")
    for soft in ("deceptive link: shows gov.uz, opens evil.cc", "app download link: a.apk",
                 "app file attached: a.apk", "link flood: the same message from several accounts",
                 None):
        assert not lc.is_severe(soft)


# --- VirusTotal ------------------------------------------------------------------

def test_flagged_domain_blocks(monkeypatch):
    calls = _fake_vt(monkeypatch, {"whitestake.cc": (7, True)})
    t = "Yordam: https://uzbekistan.whitestake.cc/form"
    reason = asyncio.run(lc.check_message(_msg(t, [_entity(t, "https://uzbekistan.whitestake.cc/form", "url")])))
    assert reason == "malicious link: VirusTotal flags whitestake.cc (7 engines)"
    assert [d for d, _k in calls] == ["uzbekistan.whitestake.cc", "whitestake.cc"]   # parent too
    assert lc.is_severe(reason)


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


def test_verdicts_are_cached_across_keys(monkeypatch):
    calls = _fake_vt(monkeypatch, {"evil.cc": (5, True)})
    for key in ("k1", "k1", "k2"):
        assert asyncio.run(lc.malicious_count("evil.cc", key)) == 5
    assert len(calls) == 1          # a domain's reputation doesn't depend on whose key asked


def test_failures_are_not_cached_and_let_the_message_pass(monkeypatch):
    calls = []

    async def broken(domain, api_key):
        calls.append(domain)
        return None
    monkeypatch.setattr(lc, "_vt_lookup", broken)
    t = "https://evil.cc"
    assert asyncio.run(lc.check_message(_msg(t, [_entity(t, t, "url")]))) is None
    assert asyncio.run(lc.malicious_count("evil.cc", "test-key")) is None
    assert calls == ["evil.cc", "evil.cc"]


def test_each_key_has_its_own_budget(monkeypatch):
    calls = _fake_vt(monkeypatch, {})
    monkeypatch.setattr(lc, "_MINUTE_LIMIT", 1)
    assert asyncio.run(lc.malicious_count("a.cc", "k1")) == 0
    assert asyncio.run(lc.malicious_count("b.cc", "k1")) is None      # k1 spent
    assert asyncio.run(lc.malicious_count("b.cc", "k2")) == 0          # k2 untouched
    assert calls == [("a.cc", "k1"), ("b.cc", "k2")]


def test_no_key_means_no_lookups_but_free_checks_still_run(monkeypatch):
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
        if request.headers.get("x-apikey") != "test-key":
            return web.json_response({"error": {"code": "WrongCredentialsError"}}, status=401)
        d = request.match_info["d"]
        if d in ("evil.cc", "google.com"):
            return web.json_response({"data": {"attributes": {"last_analysis_stats": {
                "malicious": 6 if d == "evil.cc" else 0, "harmless": 50}}}})
        return web.json_response({"error": {"code": "NotFoundError"}}, status=404)

    async def run():
        app = web.Application()
        app.router.add_get("/api/v3/domains/{d}", domains)
        server = TestServer(app)
        await server.start_server()
        try:
            monkeypatch.setattr(lc, "_VT_DOMAIN_URL",
                                f"http://{server.host}:{server.port}/api/v3/domains/{{}}")
            return (await lc._vt_lookup("evil.cc", "test-key"),
                    await lc._vt_lookup("new.cc", "test-key"),
                    await lc._vt_lookup("evil.cc", "bad-key"),
                    await lc.key_works("test-key"),
                    await lc.key_works("bad-key"))
        finally:
            await server.close()

    assert asyncio.run(run()) == ((6, True), (0, False), None, True, False)
    assert seen_keys == ["test-key", "test-key", "bad-key", "test-key", "bad-key"]


# --- handler ---------------------------------------------------------------------

def _handler_setup(monkeypatch, check_reason=None):
    """Wire handle_spam_detection to fakes; return what it deleted, blocked, alerted."""
    rec = {"deleted": [], "blocked": [], "alerts": [], "announced": []}

    class Bot:
        async def delete_message(self, chat_id, message_id):
            rec["deleted"].append(message_id)

    async def no(*a, **k):
        return False

    async def nothing(*a, **k):
        return None

    async def block(bot, chat_id, user_id, reason, user_type="human", is_permanent=False, ban=False):
        rec["blocked"].append({"reason": reason, "user_type": user_type,
                               "permanent": is_permanent, "ban": ban})

    async def alert(bot, message, reason, user_type):
        rec["alerts"].append(reason)

    async def announce(*a, **k):
        rec["announced"].append(a)

    def ai_must_not_run(*a, **k):
        raise AssertionError("a link hit must not cost a Gemini call")

    monkeypatch.setattr(sd.groups, "is_allowed", lambda cid: True)
    monkeypatch.setattr(sd, "_sender_is_admin", no)
    monkeypatch.setattr(profile_checker, "check_profile", nothing)
    monkeypatch.setattr(sd, "_report_spam", nothing)
    monkeypatch.setattr(sd, "announce_mute", announce)
    monkeypatch.setattr(sd, "block_user", block)
    monkeypatch.setattr(sd, "notify_admins", alert)
    monkeypatch.setattr(sd, "classify_spam", ai_must_not_run)
    if check_reason is not None:
        async def check(message):
            return check_reason
        monkeypatch.setattr(sd.linkcheck, "check_message", check)
    sd._profile_checked.clear()
    sd._clear_burst_chat(-100)
    return Bot(), rec


def _group_msg(bot, text, entities=None, document=None):
    return SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup", title="T"),
        from_user=SimpleNamespace(id=5, full_name="U", username="u", is_bot=False),
        sender_chat=None, message_id=77, text=text, caption=None,
        entities=entities, caption_entities=None, document=document, bot=bot)


def test_disguised_link_mutes_without_calling_ai(monkeypatch):
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    bot, rec = _handler_setup(monkeypatch)
    ents = [_entity(SCAM, "https://gov.uz/viplata2026", url="https://uzbekistan.whitestake.cc/")]
    asyncio.run(sd.handle_spam_detection(_group_msg(bot, SCAM, ents)))
    assert rec["deleted"] == [77]
    assert rec["blocked"] == [{"reason": "deceptive link: shows gov.uz, opens uzbekistan.whitestake.cc",
                               "user_type": "human", "permanent": False, "ban": False}]
    assert len(rec["announced"]) == 1 and rec["alerts"] == [rec["blocked"][0]["reason"]]


def test_virustotal_confirmed_link_bans(monkeypatch):
    reason = "malicious link: VirusTotal flags whitestake.cc (15 engines)"
    bot, rec = _handler_setup(monkeypatch, check_reason=reason)
    asyncio.run(sd.handle_spam_detection(_group_msg(bot, "https://whitestake.cc/x")))
    assert rec["deleted"] == [77]
    assert rec["blocked"] == [{"reason": reason, "user_type": "bot", "permanent": True, "ban": True}]
    assert rec["announced"] == []                 # a ban isn't announced as a 24h mute
    assert rec["alerts"] == [reason]


def test_app_file_without_caption_is_checked(monkeypatch):
    # An .apk needs no caption; before, captionless messages were skipped entirely.
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    bot, rec = _handler_setup(monkeypatch)
    msg = _group_msg(bot, None, document=SimpleNamespace(file_name="Click_yangi.apk"))
    asyncio.run(sd.handle_spam_detection(msg))
    assert rec["deleted"] == [77]
    assert rec["blocked"][0] == {"reason": "app file attached: Click_yangi.apk",
                                 "user_type": "human", "permanent": False, "ban": False}


def test_captionless_ordinary_file_is_left_alone(monkeypatch):
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    bot, rec = _handler_setup(monkeypatch)
    msg = _group_msg(bot, None, document=SimpleNamespace(file_name="kurs.pdf"))
    asyncio.run(sd.handle_spam_detection(msg))
    assert rec["deleted"] == [] and rec["blocked"] == []
