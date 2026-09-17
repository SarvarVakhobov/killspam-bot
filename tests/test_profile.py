"""Run: python -m tests.test_profile  (or pytest). No network/model required.

Locks in the multi-photo profile scan: a clean first picture must not hide an
explicit later one. Telegram + NudeNet are faked; we only test the scan logic.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.core import nsfw
from spam_bot.handlers import profile_checker as pc


class _Buf:
    def __init__(self, b): self._b = b
    def read(self): return self._b


class _FakeBot:
    """Serves `n` profile photos; each photo's bytes are b'pic{i}'."""
    def __init__(self, n): self.n = n
    async def get_chat(self, uid): return SimpleNamespace(bio="")
    async def get_user_profile_photos(self, uid, limit=1):
        photos = [[SimpleNamespace(file_id=f"pic{i}")] for i in range(min(self.n, limit))]
        return SimpleNamespace(total_count=self.n, photos=photos)
    async def get_file(self, file_id): return SimpleNamespace(file_path=file_id)
    async def download_file(self, path): return _Buf(path.encode())


def _check(n, verdict_for):
    """Run check_profile with `n` photos; nsfw verdict picked by `verdict_for(bytes)`."""
    orig = nsfw.check
    nsfw.check = verdict_for
    try:
        return asyncio.run(pc.check_profile(_FakeBot(n), SimpleNamespace(id=1)))
    finally:
        nsfw.check = orig


def test_explicit_later_photo_is_caught():
    # 3 photos, only the 2nd (b'pic1') is explicit.
    r = _check(3, lambda b: b == b"pic1")
    assert r == "profile photo #2 flagged explicit (NudeNet)", r


def test_all_clean_photos_pass():
    assert _check(3, lambda b: False) is None


def test_ambiguous_photo_takes_no_action():
    # An uncertain (None) verdict must NOT flag — we only act on clearly explicit.
    assert _check(3, lambda b: None if b == b"pic1" else False) is None


# --- Bio detection: the "clean message, payload in bio" escape tactic ---------

class _BioBot(_FakeBot):
    """Like _FakeBot but serves a chosen bio and no photos."""
    def __init__(self, bio):
        super().__init__(0)
        self._bio = bio
    async def get_chat(self, uid):
        return SimpleNamespace(bio=self._bio)


def _check_bio(bio):
    return asyncio.run(pc.check_profile(_BioBot(bio), SimpleNamespace(id=1), group_id=None))


def test_bio_own_channel_invite_link_not_blocked():
    # Regression (2026-09-16): three real members were muted for listing their own
    # channel's private invite link in their bio. A link alone never blocks now.
    assert _check_bio("Kanalim 👉 t.me/+AbCdEf12") is None
    assert _check_bio("https://t.me/joinchat/AbCdEf") is None


_APP_REASON = "profile bio links a downloadable app (likely malware)"


def test_bio_app_download_link_mutes_not_bans():
    # An app link in a bio is a common account-stealing lure: caught, but as a soft
    # reason (24h mute, admin can undo), never a ban.
    assert _check_bio("Salom! yuklab oling: http://x.site/app.apk") == _APP_REASON
    assert _check_bio("download: best-app.apk") == _APP_REASON
    assert _check_bio("https://files.io/setup.exe") == _APP_REASON
    assert not pc.is_severe(_APP_REASON)


def test_bio_explicit_link_outranks_app_link():
    assert _check_bio("🔞 t.me/xxx_channel app.apk") == "profile bio links to explicit/adult content"


_EXPLICIT_REASON = "profile bio links to explicit/adult content"


def test_bio_explicit_channel_link_is_caught():
    # Link + adult terms -> blocked, key or not.
    assert _check_bio("🔞 hot videos 👉 t.me/xxx_channel") == _EXPLICIT_REASON


def test_bio_onlyfans_domain_is_caught():
    assert _check_bio("free content onlyfans.com/someone") == _EXPLICIT_REASON


def test_bio_explicit_terms_without_link_not_hard_blocked():
    # No link -> left to the AI classifier (none here, no key) rather than a regex block.
    assert _check_bio("intim suhbatlar") is None


def test_legit_telegram_channel_in_bio_not_blocked():
    # A real user listing their own channel must NOT be auto-blocked (no key -> no AI).
    assert _check_bio("Mening kanalim: t.me/python_uz") is None


def test_legit_website_in_bio_not_blocked():
    assert _check_bio("Portfolio: https://github.com/me  @myhandle") is None


def test_clean_bio_passes():
    assert _check_bio("Talaba. Toshkent.") is None


# --- check_bio (used by the first-message scan in spam_detector) ---------------

def test_check_bio_flags_explicit_link():
    assert asyncio.run(pc.check_bio(_BioBot("🔞 t.me/xxx_channel"), 1, None)) == _EXPLICIT_REASON


def test_check_bio_clean_returns_none():
    assert asyncio.run(pc.check_bio(_BioBot("Talaba. Toshkent."), 1, None)) is None


def test_check_bio_no_bio_returns_none():
    assert asyncio.run(pc.check_bio(_BioBot(""), 1, None)) is None


# --- is_severe: which reasons trigger ban + delete vs soft mute -----------------

def test_is_severe_true_for_nudity_and_explicit_link():
    assert pc.is_severe("profile photo #2 flagged explicit (NudeNet)")
    assert pc.is_severe(_EXPLICIT_REASON)


def test_is_severe_false_for_soft_reasons_and_none():
    assert not pc.is_severe("profile photo ambiguous — needs admin review")
    assert not pc.is_severe("profile bio flagged (adult)")
    assert not pc.is_severe("profile bio links a downloadable app (likely malware)")
    assert not pc.is_severe(None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
