"""Run: python -m pytest tests/test_burst.py  (no DB/network).

Guards the link-flood detector: the same message *with a link* from 3+ accounts in
2 minutes deletes every copy and MUTES each sender (a ban only when VirusTotal
confirms the link); messages without a link, one account repeating itself, and
short chatter never trip it; a flag expires with its window.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.handlers import admin_notifier as an
from spam_bot.handlers import profile_checker
from spam_bot.handlers import spam_detector as sd

LINK_MSG = "Bepul kurs! Ro'yxatdan o'ting: https://free-course.cc/join"
NORM = sd.patterns.normalize(LINK_MSG)


def _msg(user_id, message_id, text=LINK_MSG, chat_id=-100, bot=None):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type="supergroup", title="T"),
        from_user=SimpleNamespace(id=user_id, full_name=f"User{user_id}", username=None, is_bot=False),
        sender_chat=None, message_id=message_id, text=text, caption=None,
        entities=None, caption_entities=None, document=None, bot=bot)


# --- recording -------------------------------------------------------------------

def test_three_senders_make_a_flood():
    sd._clear_burst_chat(1)
    assert sd._record_burst(_msg(100, 1, chat_id=1), NORM) == (False, None)
    assert sd._record_burst(_msg(101, 2, chat_id=1), NORM) == (False, None)
    is_flood, cohort = sd._record_burst(_msg(102, 3, chat_id=1), NORM)
    assert is_flood and cohort == [(100, 1, "User100"), (101, 2, "User101"), (102, 3, "User102")]
    assert sd._record_burst(_msg(103, 4, chat_id=1), NORM) == (True, None)   # later copy


def test_one_user_repeating_is_not_a_flood():
    sd._clear_burst_chat(2)
    for mid in range(5):
        last = sd._record_burst(_msg(500, mid, chat_id=2), NORM)
    assert last == (False, None)


def test_short_messages_ignored():
    sd._clear_burst_chat(3)
    for uid in (1, 2, 3, 4):
        assert sd._record_burst(_msg(uid, uid, chat_id=3), "t.me/x") == (False, None)


def test_flag_expires_with_the_window(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sd, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    sd._clear_burst_chat(4)
    for uid in (1, 2, 3):
        sd._record_burst(_msg(uid, uid, chat_id=4), NORM)
    clock[0] += sd._BURST_WINDOW + 1
    assert sd._record_burst(_msg(9, 9, chat_id=4), NORM) == (False, None)   # starts afresh


# --- handler ---------------------------------------------------------------------

def _setup(monkeypatch, link_reason=None):
    rec = {"deleted": [], "blocked": [], "alerts": [], "burst_alerts": []}

    class Bot:
        async def delete_message(self, chat_id, message_id):
            rec["deleted"].append(message_id)

    async def no(*a, **k):
        return False

    async def nothing(*a, **k):
        return None

    async def check(message):
        return link_reason

    async def block(bot, chat_id, user_id, reason, user_type="human", is_permanent=False, ban=False):
        rec["blocked"].append((user_id, ban, is_permanent))

    async def alert(bot, message, reason, user_type):
        rec["alerts"].append(message.from_user.id)

    async def burst_alert(bot, message, reason, actioned, banned=False):
        rec["burst_alerts"].append((actioned, banned))

    monkeypatch.setattr(sd.groups, "is_allowed", lambda cid: True)
    monkeypatch.setattr(sd, "_sender_is_admin", no)
    monkeypatch.setattr(profile_checker, "check_profile", nothing)
    monkeypatch.setattr(sd.linkcheck, "check_message", check)
    monkeypatch.setattr(sd, "classify_spam", lambda *a, **k: None)
    monkeypatch.setattr(sd, "_report_spam", nothing)
    monkeypatch.setattr(sd, "announce_mute", nothing)
    monkeypatch.setattr(sd, "block_user", block)
    monkeypatch.setattr(sd, "notify_admins", alert)
    monkeypatch.setattr(sd, "notify_admins_burst", burst_alert)
    sd._profile_checked.clear()
    sd._clear_burst_chat(-100)
    return Bot(), rec


def _send(bot, user_id, message_id, text=LINK_MSG):
    asyncio.run(sd.handle_spam_detection(_msg(user_id, message_id, text=text, bot=bot)))


def test_link_flood_mutes_everyone_and_deletes_every_copy(monkeypatch):
    bot, rec = _setup(monkeypatch)
    for uid, mid in ((100, 1), (101, 2), (102, 3)):
        _send(bot, uid, mid)
    assert sorted(rec["deleted"]) == [1, 2, 3]
    assert rec["blocked"] == [(100, False, False), (101, False, False), (102, False, False)]
    assert rec["burst_alerts"] == [([(100, "User100"), (101, "User101"), (102, "User102")], False)]


def test_later_copy_is_muted_on_its_own(monkeypatch):
    bot, rec = _setup(monkeypatch)
    for uid, mid in ((100, 1), (101, 2), (102, 3), (103, 4)):
        _send(bot, uid, mid)
    assert 4 in rec["deleted"] and (103, False, False) in rec["blocked"]
    assert rec["alerts"] == [103]


def test_greetings_without_a_link_never_flood(monkeypatch):
    bot, rec = _setup(monkeypatch)
    for uid in (100, 101, 102, 103):
        _send(bot, uid, uid, text="Assalomu alaykum hammaga!")
    assert rec["deleted"] == [] and rec["blocked"] == []


def test_flood_of_a_virustotal_confirmed_link_bans(monkeypatch):
    bot, rec = _setup(monkeypatch, link_reason="malicious link: VirusTotal flags free-course.cc (9 engines)")
    _send(bot, 100, 1)   # banned on its own already
    assert rec["blocked"] == [(100, True, True)]


def test_flood_alert_offers_unmute_per_account(monkeypatch):
    sent = []

    async def capture(bot, chat_id, text, reply_markup=None):
        sent.append((text, reply_markup))
    monkeypatch.setattr(an, "notify_group", capture)
    msg = _msg(100, 1)
    actioned = [(uid, f"User{uid}") for uid in range(100, 112)]
    asyncio.run(an.notify_admins_burst(None, msg, "link flood", actioned))
    text, kb = sent[0]
    assert "12 accounts" in text and "muted for 24h" in text
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert buttons[0] == "act:unmute:-100:100" and len(buttons) == 10   # capped

    asyncio.run(an.notify_admins_burst(None, msg, "malicious link", actioned[:3], banned=True))
    text, kb = sent[1]
    assert "banned" in text and kb is None
