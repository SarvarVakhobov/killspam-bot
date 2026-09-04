"""Per-group Gemini token accounting: record each call, aggregate for /tokens and
the daily report, and estimate cost in USD.

Pure BYOK means each group pays on its own key, so usage is attributed per group_id.
Timestamps are stored in UTC (datetime.utcnow); day boundaries are computed in
Asia/Tashkent (fixed UTC+5, no DST) so "yesterday" matches the operator's calendar.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from .config import GEMINI_MODEL, GEMINI_PRICE_IN, GEMINI_PRICE_OUT

# $ per 1M tokens (input, output). Keyed on the configured model; cost_usd falls back
# to these rates for any other model name, so historic rows still price out.
PRICING = {GEMINI_MODEL: (GEMINI_PRICE_IN, GEMINI_PRICE_OUT)}
_DEFAULT_MODEL = GEMINI_MODEL

_TASHKENT = timedelta(hours=5)            # Uzbekistan, no DST
_REPORT_STATE_KEY = "last_token_report_date"


# --- recording ----------------------------------------------------------------

def record(group_id, model: str, prompt_tokens: int, completion_tokens: int,
           total_tokens: int) -> None:
    """Insert one usage row. Best-effort: a DB hiccup must never break classification."""
    from ..db.session import SessionLocal
    from ..db.models import TokenUsage
    try:
        with SessionLocal() as db:
            db.add(TokenUsage(
                group_id=group_id, model=model,
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
                total_tokens=total_tokens or 0,
            ))
            db.commit()
    except Exception as e:
        logging.error(f"usage.record failed: {e}")


# --- cost ----------------------------------------------------------------------

def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rin, rout = PRICING.get(model, PRICING[_DEFAULT_MODEL])
    return prompt_tokens / 1_000_000 * rin + completion_tokens / 1_000_000 * rout


# --- time windows (Tashkent calendar, returned as UTC bounds) ------------------

def yesterday_bounds_utc(now_utc=None):
    """UTC [start, end) covering the previous full Tashkent calendar day."""
    now_utc = now_utc or datetime.utcnow()
    today0_tash = (now_utc + _TASHKENT).replace(hour=0, minute=0, second=0, microsecond=0)
    start_tash = today0_tash - timedelta(days=1)
    return start_tash - _TASHKENT, today0_tash - _TASHKENT


def rolling_bounds_utc(days: int, now_utc=None):
    """UTC [start, end) for a rolling N-day window ending now."""
    now_utc = now_utc or datetime.utcnow()
    return now_utc - timedelta(days=days), now_utc


def seconds_until_hour(hour: int, now_utc=None) -> float:
    """Seconds from now until the next `hour`:00 Asia/Tashkent."""
    now_utc = now_utc or datetime.utcnow()
    now_tash = now_utc + _TASHKENT
    target = now_tash.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now_tash:
        target += timedelta(days=1)
    return (target - now_tash).total_seconds()


def tashkent_today_str(now_utc=None) -> str:
    now_utc = now_utc or datetime.utcnow()
    return (now_utc + _TASHKENT).strftime("%Y-%m-%d")


# --- aggregation ---------------------------------------------------------------

def summary(start_utc, end_utc, group_id=None):
    """Sum tokens grouped by (group_id, model) over [start_utc, end_utc).
    Returns rows of (group_id, model, prompt, completion, total)."""
    from sqlalchemy import func
    from ..db.session import SessionLocal
    from ..db.models import TokenUsage
    try:
        with SessionLocal() as db:
            q = db.query(
                TokenUsage.group_id, TokenUsage.model,
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.total_tokens),
            ).filter(TokenUsage.created_at >= start_utc, TokenUsage.created_at < end_utc)
            if group_id is not None:
                q = q.filter(TokenUsage.group_id == group_id)
            rows = q.group_by(TokenUsage.group_id, TokenUsage.model).all()
        return [(gid, model, int(p or 0), int(c or 0), int(t or 0))
                for gid, model, p, c, t in rows]
    except Exception as e:
        logging.error(f"usage.summary failed: {e}")
        return []


# --- formatting ----------------------------------------------------------------

def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _fmt_usd(x: float) -> str:
    return f"${x:,.4f}"


def format_window(rows, label: str, per_group: bool = False) -> str:
    """Render one period. per_group=True breaks the lines down by group (operator
    view); otherwise rows are aggregated by model (single-group view)."""
    lines = [f"📊 {label}"]
    if not rows:
        lines.append("  (no usage)")
        return "\n".join(lines)

    grand_tok, grand_cost = 0, 0.0
    if per_group:
        by_group = defaultdict(list)
        for r in rows:
            by_group[r[0]].append(r)
        for gid, grp in by_group.items():
            lines.append(f"  Group {gid}:")
            for _, model, p, c, t in grp:
                cost = cost_usd(model, p, c)
                grand_tok += t
                grand_cost += cost
                lines.append(f"    • {model} — {_fmt_tokens(t)} tokens — {_fmt_usd(cost)}")
    else:
        agg = defaultdict(lambda: [0, 0, 0])
        for _, model, p, c, t in rows:
            a = agg[model]
            a[0] += p
            a[1] += c
            a[2] += t
        for model, (p, c, t) in agg.items():
            cost = cost_usd(model, p, c)
            grand_tok += t
            grand_cost += cost
            lines.append(f"  • {model} — {_fmt_tokens(t)} tokens — {_fmt_usd(cost)}")
    lines.append(f"  Total: {_fmt_tokens(grand_tok)} tokens — {_fmt_usd(grand_cost)}")
    return "\n".join(lines)


def tokens_report(group_id=None) -> str:
    """Full /tokens message: yesterday + last 7 + last 30 days. group_id=None gives
    the operator's global, per-group breakdown."""
    per_group = group_id is None
    windows = [
        (yesterday_bounds_utc(), "Yesterday"),
        (rolling_bounds_utc(7), "Last 7 days"),
        (rolling_bounds_utc(30), "Last 30 days"),
    ]
    header = "📈 Token usage (all groups)" if per_group else "📈 Token usage (this group)"
    parts = [header]
    for (start, end), label in windows:
        parts.append(format_window(summary(start, end, group_id), label, per_group=per_group))
    return "\n\n".join(parts)


def daily_report(group_id=None) -> str:
    """Yesterday-only report for the morning DM. group_id=None = global per-group view."""
    start, end = yesterday_bounds_utc()
    title = ("Yesterday's token usage (all groups)" if group_id is None
             else "Yesterday's token usage")
    return format_window(summary(start, end, group_id), title, per_group=group_id is None)


# --- daily-report dedupe guard (survives restarts) -----------------------------

def already_reported(date_str: str) -> bool:
    from ..db.session import SessionLocal
    from ..db.models import AppState
    try:
        with SessionLocal() as db:
            row = db.get(AppState, _REPORT_STATE_KEY)
            return bool(row and row.value == date_str)
    except Exception:
        return False


def mark_reported(date_str: str) -> None:
    from ..db.session import SessionLocal
    from ..db.models import AppState
    try:
        with SessionLocal() as db:
            row = db.get(AppState, _REPORT_STATE_KEY)
            if row:
                row.value = date_str
            else:
                db.add(AppState(key=_REPORT_STATE_KEY, value=date_str))
            db.commit()
    except Exception as e:
        logging.error(f"usage.mark_reported failed: {e}")
