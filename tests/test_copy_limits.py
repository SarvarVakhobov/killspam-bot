"""Run: python -m pytest tests/test_copy_limits.py  (no DB/network).

Telegram rejects a message over 4096 characters and a bot description over 512,
so an over-long help or setup text silently breaks the command that sends it.
"""
from spam_bot.core import copy

_MESSAGE_LIMIT = 4096


def test_every_sent_text_fits_one_message():
    sent = {"START_TEXT": copy.START_TEXT, "SETUP_TEXT": copy.SETUP_TEXT,
            "PRIVACY_TEXT": copy.PRIVACY_TEXT}
    sent.update({f"HELP_PARTS[{i}]": part for i, part in enumerate(copy.HELP_PARTS)})
    for name, text in sent.items():
        assert len(text) <= _MESSAGE_LIMIT, f"{name} is {len(text)} chars"


def test_help_parts_cover_both_languages():
    uz, en = copy.HELP_PARTS
    assert "/setvtkey" in uz and "/setvtkey" in en


def test_descriptions_fit_telegram_limit():
    assert len(copy.DESCRIPTION_UZ) <= 512 and len(copy.DESCRIPTION_EN) <= 512
