"""Run: python -m pytest tests/test_operator_alerts.py
Guards the operator ban/mute feed: it must name the group, stay off by default,
and never let a delivery failure break the moderation action that triggered it.
"""
import asyncio

from spam_bot.handlers import admin_notifier as a


class _U:
    def __init__(self, uid, name="Spammer", username=None):
        self.id, self.full_name, self.username = uid, name, username

class _Member:
    def __init__(self, user): self.user = user

class _Chat:
    def __init__(self, title): self.title = title

class _Bot:
    """Records DMs; get_chat/get_chat_member behave like a healthy Telegram."""
    def __init__(self, title="Test Guruh", member=True):
        self.sent = []
        self._title, self._member = title, member
    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text))
    async def get_chat(self, chat_id):
        return _Chat(self._title)
    async def get_chat_member(self, chat_id, user_id):
        if not self._member:
            raise RuntimeError("user not found")
        return _Member(_U(user_id, "Spammer", "spamer1"))


def _call(bot, **kw):
    kw.setdefault("chat_id", -100123)
    kw.setdefault("user_id", 4242)
    kw.setdefault("action", "🔨 BAN")
    kw.setdefault("reason", "adult spam")
    asyncio.run(a.notify_operator_action(bot, **kw))


def _setup(monkeypatch, enabled=True, admins=("777",)):
    monkeypatch.setattr(a, "OPERATOR_ALERTS", enabled)
    monkeypatch.setattr(a, "ADMIN_TELEGRAM_IDS", list(admins))
    a._chat_title_cache.clear()


def test_disabled_by_default_sends_nothing(monkeypatch):
    # The whole point of the flag: a multi-group bot must not spam the operator.
    _setup(monkeypatch, enabled=False)
    bot = _Bot()
    _call(bot)
    assert bot.sent == []


def test_no_admins_configured_sends_nothing(monkeypatch):
    _setup(monkeypatch, enabled=True, admins=())
    bot = _Bot()
    _call(bot)
    assert bot.sent == []


def test_alert_names_group_user_and_reason(monkeypatch):
    _setup(monkeypatch)
    bot = _Bot()
    _call(bot, user_type="bot")
    assert len(bot.sent) == 1
    to, text = bot.sent[0]
    assert to == "777"
    assert "Test Guruh" in text and "-100123" in text   # which group
    assert "4242" in text and "spamer1" in text         # who
    assert "adult spam" in text                         # why
    assert "🔨 BAN" in text


def test_every_operator_gets_it(monkeypatch):
    _setup(monkeypatch, admins=("777", "888"))
    bot = _Bot()
    _call(bot)
    assert sorted(cid for cid, _ in bot.sent) == ["777", "888"]


def test_unknown_user_still_reports_group_and_id(monkeypatch):
    # A banned account can already be gone; the alert must still be useful.
    _setup(monkeypatch)
    bot = _Bot(member=False)
    _call(bot)
    _, text = bot.sent[0]
    assert "4242" in text and "Test Guruh" in text


def test_get_chat_failure_falls_back_to_chat_id(monkeypatch):
    _setup(monkeypatch)
    bot = _Bot()
    async def boom(chat_id): raise RuntimeError("no access")
    bot.get_chat = boom
    _call(bot)
    _, text = bot.sent[0]
    assert "-100123" in text


def test_send_failure_never_raises(monkeypatch):
    # block_user calls this after the ban has already happened — an alert
    # problem must not surface as "Failed to block user".
    _setup(monkeypatch)
    bot = _Bot()
    async def boom(chat_id, text, reply_markup=None): raise RuntimeError("blocked bot")
    bot.send_message = boom
    _call(bot)   # must not raise
