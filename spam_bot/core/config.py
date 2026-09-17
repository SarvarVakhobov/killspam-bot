import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TELEGRAM_IDS = [x.strip() for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]
KEY_ENCRYPTION_SECRET = os.getenv("KEY_ENCRYPTION_SECRET")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", "8080"))

# Model used for AI moderation. Env-overridable: Google retires models on its own
# schedule, and a retired name fails every call with 404 (AI silently off, regex only).
# gemini-2.5-flash was the original pick but is closed to new API keys. flash-lite is
# the cheap tier — the right fit for a high-volume classifier — and it accepts
# thinking_budget=0, which the call site relies on (3.6-flash rejects it with a 400).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# Gemini pricing ($ per 1M tokens) for cost estimates in /tokens + the daily report.
# Defaults are flash-tier public rates; override per environment if they change.
GEMINI_PRICE_IN = float(os.getenv("GEMINI_PRICE_IN", "0.30"))
GEMINI_PRICE_OUT = float(os.getenv("GEMINI_PRICE_OUT", "2.50"))
# Local hour (Asia/Tashkent, UTC+5, no DST) to DM the daily usage report.
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))
# Abuse guard: max groups one non-operator admin may /enable. Operators are exempt.
MAX_GROUPS_PER_OWNER = int(os.getenv("MAX_GROUPS_PER_OWNER", "20"))
# Mirror every ban/mute to the operator DMs, with the group named. Off by default
# on purpose: notify_group keeps a group's alerts among that group's own admins,
# so a bot serving many groups doesn't turn the operator's DM into an alert dump.
# Turn it on when one person runs a small, known set of groups and wants a single
# audit feed. Operators who are also group admins will get both messages.
OPERATOR_ALERTS = os.getenv("OPERATOR_ALERTS", "0").strip().lower() in (
    "1", "true", "yes", "on")
# VirusTotal domain reputation for links posted in groups (phishing / malware).
# Empty = off; the free deceptive-link check (shown site != opened site) runs anyway.
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "").strip()
# Engines that must call a domain malicious before the bot acts. 1 would let a
# single noisy engine mute people; 2 is the usual floor for "really bad".
VT_MALICIOUS_THRESHOLD = int(os.getenv("VT_MALICIOUS_THRESHOLD", "2"))