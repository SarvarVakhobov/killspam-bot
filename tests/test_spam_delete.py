"""Run: python -m pytest tests/test_spam_delete.py  (no network/DB).

Regression: the first-message bio-scan path must DELETE the offending message,
not just mute + alert. Before the fix it left the message in the group while the
alert claimed "SPAM DETECTED — User blocked".
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.handlers import spam_detector as sd
from spam_bot.handlers import profile_checker


class FakeBot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


def _msg(bot):
    return SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup", title="T"),
        from_user=SimpleNamespace(id=5, full_name="U", username="u", is_bot=False),
        sender_chat=None, message_id=42, text="Salom", caption=None, bot=bot,
    )


def _setup(monkeypatch, reason, captured):
    sd._profile_checked.clear()
    monkeypatch.setattr(sd.groups, "is_allowed", lambda cid: True)

    async def _not_admin(m):
        return False

    async def _profile(bot_, user, gid):
        return reason

    async def _block(*a, **k):
        captured.update(k)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(sd, "_sender_is_admin", _not_admin)
    monkeypatch.setattr(profile_checker, "check_profile", _profile)
    monkeypatch.setattr(sd, "block_user", _block)
    monkeypatch.setattr(sd, "notify_admins", _noop)


def test_severe_profile_message_deleted_and_banned(monkeypatch):
    bot = FakeBot()
    msg = _msg(bot)
    captured = {}
    _setup(monkeypatch, "profile photo #1 flagged explicit (NudeNet)", captured)
    asyncio.run(sd.handle_spam_detection(msg))
    assert (msg.chat.id, msg.message_id) in bot.deleted   # message removed
    assert captured.get("ban") is True                    # account banned, not muted
    assert captured.get("is_permanent") is True


def test_soft_profile_message_deleted_not_banned(monkeypatch):
    bot = FakeBot()
    msg = _msg(bot)
    captured = {}
    _setup(monkeypatch, "profile bio flagged (adult)", captured)
    asyncio.run(sd.handle_spam_detection(msg))
    assert (msg.chat.id, msg.message_id) in bot.deleted   # still deleted
    assert captured.get("ban") is False                   # but muted pending review, not banned


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
