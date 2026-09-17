"""Run: python -m pytest tests/test_ai_switch.py  (sqlite, no network).

Guards the operator AI switch (/ai): the default is on (so untouched deploys keep
today's behaviour), "all" really reaches every group, a per-group toggle survives
until the next "all", a switched-off group never reaches Gemini or its budgets,
and only the operator can flip anything.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")
from cryptography.fernet import Fernet
os.environ.setdefault("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())

from spam_bot.db.session import engine, Base, SessionLocal
from spam_bot.db.models import AllowedGroup, GroupConfig  # noqa: F401
Base.metadata.create_all(bind=engine)

import pytest

from spam_bot.core import ai_settings, keys, patterns, stats
from spam_bot.handlers import admin_notifier as an
from spam_bot.handlers import spam_detector as sd

A, B, C = -7001, -7002, -7003


def _wipe():
    with SessionLocal() as db:
        db.query(GroupConfig).update({GroupConfig.ai_enabled: None})
        db.query(AllowedGroup).filter(AllowedGroup.chat_id.in_([A, B, C])).delete()
        db.commit()
    for cid in (A, B, C):
        keys.delete_key(cid)
    keys.delete_key(keys.GLOBAL_SCOPE)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # One shared sqlite DB for the whole suite: leftovers here would flip other
    # modules' assumptions (test_stats expects "no key -> AI off", not "switched off").
    monkeypatch.setattr(an, "ADMIN_TELEGRAM_IDS", ["777"])
    monkeypatch.setattr(patterns, "_learned", {})
    _wipe()
    yield
    _wipe()


# --- settings -------------------------------------------------------------------

def test_default_is_on_when_nothing_stored():
    assert ai_settings.default_enabled() is True
    assert ai_settings.is_enabled(A) is True


def test_all_off_reaches_every_group_including_future_ones():
    ai_settings.set_group(A, True)          # equals default -> nothing forced
    ai_settings.set_all(False)
    assert not ai_settings.is_enabled(A)
    assert not ai_settings.is_enabled(-7999)   # a group enabled later follows the default


def test_group_toggle_overrides_default_until_next_all():
    ai_settings.set_all(False)
    ai_settings.set_group(B, True)
    assert ai_settings.is_enabled(B) and not ai_settings.is_enabled(A)
    ai_settings.set_all(False)              # "all" wins: overrides are dropped
    assert not ai_settings.is_enabled(B)


def test_toggle_back_to_default_stores_follow_default():
    ai_settings.set_group(A, False)
    ai_settings.set_group(A, True)          # back to the (on) default
    with SessionLocal() as db:
        assert db.get(GroupConfig, A).ai_enabled is None
    ai_settings.set_all(False)
    assert not ai_settings.is_enabled(A)


def test_status_distinguishes_off_nokey_own_global():
    assert ai_settings.status(A) == "nokey"
    keys.set_key(keys.GLOBAL_SCOPE, "AIzaSyShared", set_by=777)
    assert ai_settings.status(A) == "global"
    keys.set_key(A, "AIzaSyOwn", set_by=1)
    assert ai_settings.status(A) == "own"
    ai_settings.set_group(A, False)
    assert ai_settings.status(A) == "off"


def test_switch_does_not_touch_the_shared_key_row():
    keys.set_key(keys.GLOBAL_SCOPE, "AIzaSyShared", set_by=777)
    ai_settings.set_all(False)
    assert keys.get_global_key() == "AIzaSyShared"
    assert keys.delete_key(keys.GLOBAL_SCOPE) is True
    assert ai_settings.default_enabled() is False   # the switch outlives the key


# --- classifier -----------------------------------------------------------------

class _NoBudget:
    def allow(self, key):
        raise AssertionError("a switched-off group must not touch the AI budgets")


def test_switched_off_group_skips_ai_before_budgets(monkeypatch):
    keys.set_key(A, "AIzaSyOwn", set_by=1)
    ai_settings.set_group(A, False)
    monkeypatch.setattr(sd, "_user_budget", _NoBudget())
    monkeypatch.setattr(sd, "_global_budget", _NoBudget())
    assert sd._classify("hello", ("k", 1), group_id=A) == (None, "skipped:ai-off")


def test_switched_on_group_without_key_stays_keyless():
    assert sd._classify("hello", ("k", 2), group_id=B) == (None, "skipped:no-AI")


def test_operator_private_check_is_not_gated():
    ai_settings.set_all(False)
    # group_id=None is the operator's forward-to-check flow — no group to switch.
    assert sd._classify("hello", ("k", 3), group_id=None)[1] != "skipped:ai-off"


def test_reported_bio_is_not_flagged_without_ai():
    # The 2026-09-16 case: own channel invite link in the bio, AI unavailable.
    assert sd.classify_spam("Kanalim 👉 t.me/+AbCdEf12", group_id=C) is None


# --- roster ---------------------------------------------------------------------

def test_roster_labels(monkeypatch):
    with SessionLocal() as db:
        db.add_all([AllowedGroup(chat_id=cid, enabled_by=1) for cid in (A, B, C)])
        db.commit()
    keys.set_key(A, "AIzaSyOwn", set_by=1)
    ai_settings.set_group(B, False)
    out = stats.report(titles={A: "Alpha", B: "Beta", C: "Gamma"})
    line = {t: next(l for l in out.splitlines() if t in l) for t in ("Alpha", "Beta", "Gamma")}
    assert line["Alpha"].endswith("AI: on")
    assert line["Beta"].endswith("AI: off (switched off)")
    assert line["Gamma"].endswith("AI: off (no key)")


# --- /ai command + buttons ------------------------------------------------------

class _Bot:
    async def get_chat(self, chat_id):
        return SimpleNamespace(title={A: "Kino guruh", B: "Python"}.get(chat_id, "?"))


class _Msg:
    def __init__(self, uid, chat_type="private"):
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(id=uid, type=chat_type)
        self.bot = _Bot()
        self.replies, self.edits = [], []

    async def reply(self, text, reply_markup=None, **kw):
        self.replies.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **kw):
        self.edits.append((text, reply_markup))


class _Cb:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.bot = _Bot()
        self.message = _Msg(uid)
        self.answers = []

    async def answer(self, text=None, **kw):
        self.answers.append(text)


def _buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def test_ai_command_refuses_non_operator():
    m = _Msg(555)
    asyncio.run(an.handle_ai_command(m))
    assert m.replies[0][0] == "This command is for the bot operator."


def test_ai_panel_lists_groups_with_toggles(monkeypatch):
    monkeypatch.setattr(an.groups, "allowed_ids", lambda: {A, B})
    keys.set_key(A, "AIzaSyOwn", set_by=1)
    m = _Msg(777)
    asyncio.run(an.handle_ai_command(m))
    text, kb = m.replies[0]
    assert "Kino guruh — AI ishlayapti (guruhning o'z kaliti)" in text
    assert "Python — yoqilgan, lekin kalit yo'q" in text and "/globalkey set" in text
    assert "AIzaSy" not in text                                   # never echo a key
    btns = _buttons(kb)
    assert ("⛔ O'chirish: Kino guruh", f"ai:g:{A}") in btns
    assert ("✅ Hammasida yoqish", "ai:all:1") in btns and ("⛔ Hammasida o'chirish", "ai:all:0") in btns


def test_group_button_toggles_and_refreshes(monkeypatch):
    monkeypatch.setattr(an.groups, "allowed_ids", lambda: {A, B})
    cb = _Cb(777, f"ai:g:{A}")
    asyncio.run(an.on_ai_toggle(cb))
    assert not ai_settings.is_enabled(A) and ai_settings.is_enabled(B)
    assert cb.answers == ["O'chirildi"]
    text, kb = cb.message.edits[0]
    assert "Kino guruh — AI o'chirilgan" in text
    assert ("✅ Yoqish: Kino guruh", f"ai:g:{A}") in _buttons(kb)


def test_all_buttons(monkeypatch):
    monkeypatch.setattr(an.groups, "allowed_ids", lambda: {A, B})
    asyncio.run(an.on_ai_toggle(_Cb(777, "ai:all:0")))
    assert not ai_settings.is_enabled(A) and not ai_settings.is_enabled(B)
    asyncio.run(an.on_ai_toggle(_Cb(777, "ai:all:1")))
    assert ai_settings.is_enabled(A) and ai_settings.is_enabled(B)


def test_buttons_refuse_non_operator():
    cb = _Cb(555, "ai:all:0")
    asyncio.run(an.on_ai_toggle(cb))
    assert cb.answers == ["Not authorized."]
    assert ai_settings.default_enabled() is True


def test_malformed_callback_is_ignored():
    for data in ("ai:g:notanumber", "ai:g", "ai:zzz"):
        cb = _Cb(777, data)
        asyncio.run(an.on_ai_toggle(cb))
        assert cb.answers == [None]
