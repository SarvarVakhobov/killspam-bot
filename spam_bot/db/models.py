from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean
from datetime import datetime
from .session import Base

# Telegram user/chat IDs exceed 32-bit INTEGER (user ids > 2.1e9, supergroup ids
# ~ -1e12), so all ID columns use BigInteger.


class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True)
    group_id = Column(BigInteger, index=True)
    reason = Column(String)
    user_type = Column(String)  # 'human' or 'bot'
    is_permanent = Column(Boolean, default=False)
    blocked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    admin_notified = Column(Boolean, default=False)
    admin_override = Column(Boolean, default=False)

class SpamReport(Base):
    __tablename__ = "spam_reports"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True)
    group_id = Column(BigInteger, index=True)
    message_text = Column(String)
    reason = Column(String)
    reported_at = Column(DateTime, default=datetime.utcnow)
    admin_notified = Column(Boolean, default=False)

class LearnedPattern(Base):
    __tablename__ = "learned_patterns"

    id = Column(Integer, primary_key=True, index=True)
    pattern = Column(String, nullable=False)      # normalized keyword/substring
    category = Column(String, nullable=False)     # 'ads' | 'inappropriate'
    added_by = Column(BigInteger)                 # admin telegram id
    group_id = Column(BigInteger, index=True)     # NULL = global; set = per-group
    created_at = Column(DateTime, default=datetime.utcnow)

class FeedbackReport(Base):
    """Admin-reported misclassification: forward a message, tag what's wrong.
    Feeds prompt/pattern tuning and a future eval set."""
    __tablename__ = "feedback_reports"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(BigInteger, index=True)
    message_text = Column(String)
    bot_verdict = Column(String)   # what classify_spam said: a reason, or 'clean'
    label = Column(String)         # 'false_positive' | 'false_negative' | 'suspicious_account'
    note = Column(String)          # optional free-text explanation
    # For 'suspicious_account': the flagged profile (the MESSAGE may be benign).
    target_user_id = Column(BigInteger, index=True)  # null if forward hid the sender
    target_name = Column(String)
    group_id = Column(BigInteger, index=True)         # NULL = global/operator-flagged
    created_at = Column(DateTime, default=datetime.utcnow)

class AppState(Base):
    """Tiny key/value store for bot-level state (e.g. last release version
    announced to admins, so a restart doesn't re-send the same notes)."""
    __tablename__ = "app_state"

    key = Column(String, primary_key=True)
    value = Column(String)

class TokenGrant(Base):
    """Single-use, short-TTL token granting access to the BYOK key-entry form."""
    __tablename__ = "token_grants"

    token = Column(String, primary_key=True)
    chat_id = Column(BigInteger, index=True)
    created_by = Column(BigInteger)        # admin who ran /setkey
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    kind = Column(String)                  # which key the form sets: "gemini" (NULL) | "vt"


class GroupConfig(Base):
    """Per-group configuration: BYOK Gemini key (encrypted). Separate from
    AllowedGroup so the key survives /disable."""
    __tablename__ = "group_config"

    chat_id = Column(BigInteger, primary_key=True, index=True)
    gemini_key_encrypted = Column(String)
    key_set_by = Column(BigInteger)
    key_set_at = Column(DateTime)
    # Operator AI switch (/ai): True/False forces AI on/off for this group; NULL
    # follows the default, stored on the keys.GLOBAL_SCOPE row (NULL there = on).
    ai_enabled = Column(Boolean)
    # The group's own VirusTotal key (/setvtkey), kept apart from the Gemini key.
    vt_key_encrypted = Column(String)
    vt_key_set_by = Column(BigInteger)
    vt_key_set_at = Column(DateTime)


class TokenUsage(Base):
    """One row per Gemini call: which group's key paid, the model, and token counts.
    Powers /tokens and the daily usage report. group_id is the group whose BYOK key
    was billed (so cost is attributable per owner)."""
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(BigInteger, index=True)
    model = Column(String)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AllowedGroup(Base):
    __tablename__ = "allowed_groups"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, index=True)
    enabled_by = Column(BigInteger)               # admin telegram id
    enabled_at = Column(DateTime, default=datetime.utcnow)
    # BYOK (future): add gemini_key here for per-group keys.
