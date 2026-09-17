"""Run: python -m tests.test_patterns  (or pytest). No DB required."""
from spam_bot.core import patterns


def test_normalize_folds_cyrillic_homoglyphs():
    # "zаrаbоtоk" written with Cyrillic а/о should fold to ASCII.
    assert patterns.normalize("ZАRАBОTОK") == "zarabotok"


def test_seed_rules_block_nothing_outside_18_plus():
    # Scope: only 18+ content blocks automatically. The private-invite-link rule
    # muted real members for listing their own channel in their bio, so the [ads]
    # seed is empty — links, promo wording and crypto talk all pass the regex layer.
    for msg in ("Kanalim: t.me/+AbCdEf12", "https://t.me/joinchat/AbCdEf",
                "🪙🪙🪙 Free Solana Case Drop — open yours now",
                "claim your free crypto reward today",
                "Сегодня большая скидка!", "я работаю программистом",
                "how do I fix this python bug?"):
        assert patterns.classify(msg) is None, msg


def test_harmless_messages_are_not_flagged():
    # Regression (v1.7.0): everyday Uzbek words that the old [flirting]/[inappropriate]
    # seed sections flagged — and permanently banned people over — must now pass clean.
    for msg in ("salom", "salom qizlar qayerdasiz?", "menga bu loyiha yoqdi",
                "sizga rahmat", "mol narxi qancha?"):
        assert patterns.classify(msg) is None, msg
        assert patterns.is_flirting(msg) is False, msg


def test_learned_keyword_matches_after_fold(monkeypatch=None):
    # Inject a global (NULL) learned keyword without touching the DB.
    patterns._learned = {None: {"ads": ["zarabotok"]}}
    assert patterns.classify("Easy zаrаbоtоk online") == "advertisement"
    patterns._learned = {}


def test_extract_keywords_pulls_urls_and_words():
    kws = patterns.extract_keywords("Zarabotok online! t.me/xyz qo'shiling")
    assert "t.me/xyz" in kws
    assert "zarabotok" in kws


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
