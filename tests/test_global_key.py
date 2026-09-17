"""Run: python -m pytest tests/test_global_key.py  (sqlite, no network).

Guards the operator's shared Gemini key: a group's own key always wins, the
shared key is only a fallback, the operator's private no-group flow never picks
it up, and only an operator can write it — through /globalkey or the web form.
"""
import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
from cryptography.fernet import Fernet
os.environ.setdefault("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())

from spam_bot.db.session import engine, Base, SessionLocal
from spam_bot.db.models import GroupConfig, TokenGrant, AllowedGroup  # noqa: F401
Base.metadata.create_all(bind=engine)

import pytest
from aiohttp.test_utils import TestClient, TestServer

from spam_bot import web as spam_web
from spam_bot.core import keys, stats, tokens
from spam_bot.handlers import admin_notifier as an
from spam_bot.handlers import spam_detector as sd

G = keys.GLOBAL_SCOPE


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # Every test module shares one DB: a shared key left behind would flip other
    # modules' "no key -> regex only" assertions (test_stats).
    monkeypatch.setattr(an, "ADMIN_TELEGRAM_IDS", ["777"])
    monkeypatch.setattr(spam_web, "ADMIN_TELEGRAM_IDS", ["777"])
    monkeypatch.setattr(spam_web, "validate_gemini_key", lambda k: True)
    keys.delete_key(G)
    yield
    keys.delete_key(G)


# --- key resolution -------------------------------------------------------------

def test_sentinel_is_not_a_real_chat_id():
    assert G == 0


def test_no_keys_means_no_ai():
    assert keys.resolve_key(-5001) == (None, None)


def test_shared_key_is_the_fallback():
    keys.set_key(G, "AIzaSyShared", set_by=777)
    assert keys.resolve_key(-5002) == ("AIzaSyShared", "global")


def test_own_key_beats_shared_key():
    keys.set_key(G, "AIzaSyShared", set_by=777)
    keys.set_key(-5003, "AIzaSyOwn", set_by=2)
    assert keys.resolve_key(-5003) == ("AIzaSyOwn", "own")


def test_no_group_never_falls_back():
    # The operator's private forward-to-check flow classifies with no group; it was
    # keyless before the shared key existed and must stay that way.
    keys.set_key(G, "AIzaSyShared", set_by=777)
    assert keys.resolve_key(None) == (None, None)


def test_delete_and_info():
    assert keys.key_info(G) is None
    assert keys.delete_key(G) is False
    keys.set_key(G, "AIzaSyShared", set_by=42)
    by, at = keys.key_info(G)
    assert by == 42 and at is not None
    assert keys.delete_key(G) is True
    assert keys.get_global_key() is None


class _FakeGenai:
    class Client:
        def __init__(self, api_key):
            self.api_key = api_key


def test_classifier_client_uses_the_resolved_key(monkeypatch):
    monkeypatch.setattr(sd, "genai", _FakeGenai)
    sd._client_cache.clear()
    assert sd._get_gemini_client(-5004) is None                  # nothing set
    keys.set_key(G, "AIzaSyShared", set_by=777)
    assert sd._get_gemini_client(-5004).api_key == "AIzaSyShared"
    keys.set_key(-5005, "AIzaSyOwn", set_by=2)
    assert sd._get_gemini_client(-5005).api_key == "AIzaSyOwn"


# --- operator roster ------------------------------------------------------------

def test_roster_counts_shared_key_as_ai_on():
    with SessionLocal() as db:
        db.add(AllowedGroup(chat_id=-5006, enabled_by=7))
        db.commit()
    try:
        inv = {cid: on for cid, _at, on in stats.group_inventory()}
        assert inv[-5006] is False
        keys.set_key(G, "AIzaSyShared", set_by=777)
        inv = {cid: on for cid, _at, on in stats.group_inventory()}
        assert inv[-5006] is True
        line = next(l for l in stats.report().splitlines() if "-5006" in l)
        assert line.endswith("AI: on (shared key)")
    finally:
        with SessionLocal() as db:
            db.query(AllowedGroup).filter(AllowedGroup.chat_id == -5006).delete()
            db.commit()


# --- web form -------------------------------------------------------------------

def _client():
    return TestClient(TestServer(spam_web.build_app()))


def test_operator_link_sets_the_shared_key_not_a_group_key():
    tok = tokens.mint(G, 777)

    async def run():
        async with _client() as c:
            page = await (await c.get(f"/key?t={tok}")).text()
            assert "shared ai key" in page.lower()
            done = await (await c.post("/key", data={"t": tok, "key": "AIzaSyShared"})).text()
            assert "shared ai key saved" in done.lower()
    asyncio.run(run())
    assert keys.get_global_key() == "AIzaSyShared"


def test_non_operator_grant_cannot_write_the_shared_key():
    tok = tokens.mint(G, 555)

    async def run():
        async with _client() as c:
            text = await (await c.post("/key", data={"t": tok, "key": "AIzaSyEvil"})).text()
            assert "can't set the shared key" in text
    asyncio.run(run())
    assert keys.get_global_key() is None


# --- /globalkey command ---------------------------------------------------------

class _Msg:
    def __init__(self, uid, chat_type="private"):
        self.from_user = type("U", (), {"id": uid})()
        self.chat = type("C", (), {"id": uid, "type": chat_type})()
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)


class _Cmd:
    def __init__(self, args=None):
        self.args = args


def test_globalkey_refuses_non_operator():
    keys.set_key(G, "AIzaSyShared", set_by=777)
    m = _Msg(555)
    asyncio.run(an.handle_globalkey_command(m, _Cmd("off")))
    assert m.replies == ["This command is for the bot operator."]
    assert keys.get_global_key() == "AIzaSyShared"               # untouched


def test_globalkey_status_then_off():
    keys.set_key(G, "AIzaSyShared", set_by=777)
    m = _Msg(777)
    asyncio.run(an.handle_globalkey_command(m, _Cmd()))
    assert "YOQILGAN" in m.replies[0] and "AIzaSy" not in m.replies[0]   # never echo the key
    asyncio.run(an.handle_globalkey_command(m, _Cmd("off")))
    assert keys.get_global_key() is None
    assert "o'chirildi" in m.replies[1]


def test_deep_link_cannot_reach_the_shared_scope():
    # Even for the operator, ?start=setkey-0 must not mint a shared-scope link.
    def minted():
        with SessionLocal() as db:
            return db.query(TokenGrant).filter(TokenGrant.chat_id == G).count()
    before = minted()
    m = _Msg(777)
    asyncio.run(an._start_setkey(m, G))
    assert "isn't protected" in m.replies[0]
    assert minted() == before
