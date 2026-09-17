"""Run: python -m pytest tests/test_vt_key.py  (sqlite, no network).

Guards VirusTotal keys, set the same way as Gemini keys: stored encrypted apart
from the Gemini key; resolved group key -> operator's shared key -> server .env;
entered through the one-time web form and validated against VirusTotal (never
Gemini); the shared key writable only by an operator; /setvtkey and /globalvtkey
behave like /setkey and /globalkey.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")
from cryptography.fernet import Fernet
os.environ.setdefault("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())

from spam_bot.db.session import engine, Base
from spam_bot.db.models import GroupConfig, TokenGrant  # noqa: F401
Base.metadata.create_all(bind=engine)

import pytest
from aiogram.types import MessageEntity
from aiohttp.test_utils import TestClient, TestServer

from spam_bot import web as spam_web
from spam_bot.core import config, crypto, keys, linkcheck as lc, tokens
from spam_bot.handlers import admin_notifier as an

G, A = keys.GLOBAL_SCOPE, -8001


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(an, "ADMIN_TELEGRAM_IDS", ["777"])
    monkeypatch.setattr(spam_web, "ADMIN_TELEGRAM_IDS", ["777"])
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "")
    lc._cache.clear()
    lc._budgets.clear()

    def gemini_must_not_validate(key):
        raise AssertionError("a VirusTotal key must not be checked against Gemini")
    monkeypatch.setattr(spam_web, "validate_gemini_key", gemini_must_not_validate)

    async def vt_ok(key):
        return True
    monkeypatch.setattr(spam_web, "validate_vt_key", vt_ok)
    yield
    for scope in (A, G):
        for kind in ("gemini", "vt"):
            keys.delete_key(scope, kind)


# --- storage & resolution ---------------------------------------------------------

def test_vt_and_gemini_keys_live_side_by_side():
    keys.set_key(A, "AIzaSyGem", set_by=1)
    keys.set_key(A, "vt-own", set_by=2, kind="vt")
    assert keys.get_key(A) == "AIzaSyGem" and keys.get_key(A, "vt") == "vt-own"
    assert keys.key_info(A, "vt")[0] == 2
    assert keys.delete_key(A, "vt") is True
    assert keys.get_key(A) == "AIzaSyGem" and keys.get_key(A, "vt") is None


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        keys.get_key(A, "nope")


def test_group_key_then_shared_key_then_server_env(monkeypatch):
    assert lc.vt_key_for(A) is None
    monkeypatch.setattr(lc, "VIRUSTOTAL_API_KEY", "env-key")
    assert lc.vt_key_for(A) == "env-key"
    keys.set_key(G, "vt-shared", set_by=777, kind="vt")
    assert lc.vt_key_for(A) == "vt-shared"
    keys.set_key(A, "vt-own", set_by=1, kind="vt")
    assert lc.vt_key_for(A) == "vt-own"
    assert lc.vt_key_for(None) == "env-key"          # no group: server key only


def test_link_check_spends_the_groups_own_key(monkeypatch):
    keys.set_key(A, "vt-own", set_by=1, kind="vt")
    used = []

    async def lookup(domain, api_key):
        used.append(api_key)
        return 0, True
    monkeypatch.setattr(lc, "_vt_lookup", lookup)
    t = "https://some-shop.cc/sale"
    msg = SimpleNamespace(text=t, caption=None, caption_entities=None, document=None,
                          entities=[MessageEntity(type="url", offset=0, length=len(t))],
                          chat=SimpleNamespace(id=A))
    assert asyncio.run(lc.check_message(msg)) is None
    assert used == ["vt-own"]


def test_grant_carries_its_kind():
    assert tokens.validate(tokens.mint(A, 1, "vt"))["kind"] == "vt"
    assert tokens.validate(tokens.mint(A, 1))["kind"] == "gemini"


# --- web form ---------------------------------------------------------------------

def _client():
    return TestClient(TestServer(spam_web.build_app()))


def _form(tok, key):
    async def run():
        async with _client() as c:
            page = await (await c.get(f"/key?t={tok}")).text()
            done = await (await c.post("/key", data={"t": tok, "key": key})).text()
            return page, done
    return asyncio.run(run())


def test_form_stores_a_vt_key_not_a_gemini_key():
    page, done = _form(tokens.mint(A, 5, "vt"), "vt-own")
    assert "VirusTotal" in page and "Gemini" not in page
    assert "virustotal link checks" in done.lower()
    assert keys.get_key(A, "vt") == "vt-own" and keys.get_key(A) is None


def test_rejected_vt_key_is_not_stored(monkeypatch):
    async def vt_bad(key):
        return False
    monkeypatch.setattr(spam_web, "validate_vt_key", vt_bad)
    _page, done = _form(tokens.mint(A, 5, "vt"), "vt-wrong")
    assert "didn't work" in done and keys.get_key(A, "vt") is None


def test_shared_vt_key_only_from_an_operator():
    _page, done = _form(tokens.mint(G, 555, "vt"), "vt-evil")
    assert "can't set the shared key" in done and keys.get_global_key("vt") is None
    page, done = _form(tokens.mint(G, 777, "vt"), "vt-shared")
    assert "shared virustotal key" in page.lower() and "shared virustotal key saved" in done.lower()
    assert keys.get_global_key("vt") == "vt-shared"


# --- commands ---------------------------------------------------------------------

class _Bot:
    def __init__(self):
        self.dms = []

    async def delete_message(self, chat_id, message_id):
        pass

    async def send_message(self, chat_id, text, **kw):
        self.dms.append((chat_id, text))


def test_setvtkey_dms_a_virustotal_link(monkeypatch):
    monkeypatch.setattr(an.groups, "is_allowed", lambda cid: True)

    async def is_admin(message):
        return True
    monkeypatch.setattr(an, "_is_group_admin", is_admin)
    monkeypatch.setattr(crypto, "available", lambda: True)
    monkeypatch.setattr(config, "BASE_URL", "http://bot.local:8090")
    bot = _Bot()
    msg = SimpleNamespace(chat=SimpleNamespace(id=A, type="supergroup"), message_id=1, bot=bot,
                          from_user=SimpleNamespace(id=4242, first_name="Ali"))
    asyncio.run(an.handle_setvtkey_command(msg))
    (to, text), = bot.dms
    assert to == 4242 and "VirusTotal key" in text
    tok = text.split("/key?t=")[1].split()[0]
    grant = tokens.validate(tok)
    assert grant["kind"] == "vt" and grant["chat_id"] == A


def test_deep_link_routes_by_key_kind(monkeypatch):
    seen = []

    async def landing(message, chat_id, kind="gemini"):
        seen.append((chat_id, kind))
    monkeypatch.setattr(an, "_start_setkey", landing)
    for payload in (f"setvtkey-{A}", f"setkey-{A}"):
        asyncio.run(an.handle_start(SimpleNamespace(), SimpleNamespace(args=payload)))
    assert seen == [(A, "vt"), (A, "gemini")]


class _Msg:
    def __init__(self, uid):
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(id=uid, type="private")
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)


def test_globalvtkey_status_and_off_leave_gemini_alone():
    keys.set_key(G, "AIzaSyShared", set_by=777)
    keys.set_key(G, "vt-shared", set_by=777, kind="vt")
    m = _Msg(777)
    asyncio.run(an.handle_globalvtkey_command(m, SimpleNamespace(args=None)))
    assert "Umumiy VirusTotal kaliti: YOQILGAN" in m.replies[0] and "vt-shared" not in m.replies[0]
    asyncio.run(an.handle_globalvtkey_command(m, SimpleNamespace(args="off")))
    assert "o'chirildi" in m.replies[1]
    assert keys.get_global_key("vt") is None and keys.get_global_key() == "AIzaSyShared"


def test_globalvtkey_refuses_non_operator():
    m = _Msg(555)
    asyncio.run(an.handle_globalvtkey_command(m, SimpleNamespace(args="off")))
    assert m.replies == ["This command is for the bot operator."]
