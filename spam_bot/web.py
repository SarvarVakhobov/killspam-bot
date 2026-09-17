"""Key-entry web server: GET /key renders the form, POST /key stores the key,
GET /health is the liveness probe. Runs in the same asyncio loop as polling."""
import logging

from aiohttp import web

from .core import crypto, keys, tokens
from .core.config import ADMIN_TELEGRAM_IDS, GEMINI_MODEL
from .core.ratelimit import RateLimiter

try:
    from google import genai  # type: ignore
except Exception:
    genai = None

_post_limit = RateLimiter(limit=5, window=60.0)  # per token / min


def validate_gemini_key(key: str) -> bool:
    """A tiny live call confirms the key works. Monkeypatched in tests.
    Fails CLOSED: if the genai lib is missing we can't use the key anyway, so
    reject rather than store an unvalidated (and unusable) key."""
    if genai is None:
        logging.warning("validate_gemini_key: google-genai unavailable — rejecting key")
        return False
    try:
        client = genai.Client(api_key=key)
        client.models.generate_content(
            model=GEMINI_MODEL, contents="ping",
            config={"thinking_config": {"thinking_budget": 0}})
        return True
    except Exception as e:
        # Never log the exception body — it can echo the key. Log only the type.
        logging.info("key validation failed: %s", type(e).__name__)
        return False


async def validate_vt_key(key: str) -> bool:
    """A live VirusTotal lookup confirms the key works. Monkeypatched in tests."""
    from .core import linkcheck
    return await linkcheck.key_works(key)


# kind -> what the key-entry page says
_FORM = {
    "gemini": {
        "name": "Gemini",
        "own_heading": "Enable AI moderation",
        "shared_heading": "Set the shared AI key",
        "guide": "https://gemini.google.com/share/dbde5edfe69b",
        "own_done": "✅ AI moderation is on for your group.",
        "shared_done": "✅ Shared AI key saved.",
    },
    "vt": {
        "name": "VirusTotal",
        "own_heading": "Enable VirusTotal link checks",
        "shared_heading": "Set the shared VirusTotal key",
        "guide": "https://docs.virustotal.com/docs/please-give-me-an-api-key",
        "own_done": "✅ VirusTotal link checks now use your group's own key.",
        "shared_done": "✅ Shared VirusTotal key saved.",
    },
}
_EXPIRED = ("<h2>This link is invalid or has expired.</h2>"
            "<p>Run the command again in your group for a fresh link.</p>")


def _page(title: str, body: str) -> web.Response:
    html = (
        f"<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title>"
        f"<body style='font-family:system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem'>"
        f"{body}</body>"
    )
    # The /key page carries a one-time token in its URL: keep it out of referrers
    # and out of caches/back-forward history.
    return web.Response(text=html, content_type="text/html", headers={
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    })


async def get_key(request: web.Request) -> web.Response:
    grant = tokens.validate(request.query.get("t", ""))
    if not grant or grant["kind"] not in _FORM:
        return _page("Link expired", _EXPIRED)
    form = _FORM[grant["kind"]]
    shared = grant["chat_id"] == keys.GLOBAL_SCOPE
    heading = form["shared_heading"] if shared else form["own_heading"]
    scope = ("<p><b>This key will be used by every protected group that has no key "
             "of its own.</b></p>" if shared else "")
    body = (
        f"<h2>{heading}</h2>{scope}"
        f"<p>Paste your {form['name']} API key below. "
        f"<a href='{form['guide']}' target='_blank' rel='noopener noreferrer'>How to get a key</a>.</p>"
        f"<form method=post action='/key'>"
        f"<input type=hidden name=t value='{grant['token']}'>"
        f"<input name=key placeholder='{form['name']} API key' style='width:100%;padding:.5rem' autocomplete=off>"
        f"<button style='margin-top:1rem;padding:.5rem 1rem'>Save key</button></form>"
    )
    return _page(f"Set {form['name']} key", body)


async def post_key(request: web.Request) -> web.Response:
    data = await request.post()
    tok = data.get("t", "")
    key = (data.get("key") or "").strip()

    grant = tokens.validate(tok)
    if not grant or grant["kind"] not in _FORM:
        return _page("Link expired", _EXPIRED)
    kind = grant["kind"]
    form = _FORM[kind]
    shared = grant["chat_id"] == keys.GLOBAL_SCOPE
    # Defense in depth: only the operator-gated commands mint this scope, but a key
    # every keyless group falls back to must never be writable by anyone else.
    if shared and str(grant["created_by"]) not in ADMIN_TELEGRAM_IDS:
        return _page("Not allowed", "<h2>This link can't set the shared key.</h2>")
    if not _post_limit.allow(tok):
        return _page("Slow down", "<h2>Too many attempts. Wait a minute and retry.</h2>")
    if not key:
        return _page("Missing key",
                     f"<h2>No key entered.</h2><p>Go back and paste your {form['name']} key.</p>")
    works = validate_gemini_key(key) if kind == "gemini" else await validate_vt_key(key)
    if not works:
        return _page("Key rejected",
                     "<h2>That key didn't work.</h2>"
                     "<p>Check it and run the command again for a fresh link.</p>")
    if not keys.set_key(grant["chat_id"], key, grant["created_by"], kind):
        return _page("Not configured",
                     "<h2>Key storage isn't configured on this bot.</h2>"
                     "<p>Contact the bot operator.</p>")
    tokens.consume(tok)
    if shared:
        return _page("Done",
                     f"<h2>{form['shared_done']}</h2>"
                     "<p>Every protected group without its own key now uses it. "
                     "You can close this page.</p>")
    return _page("Done", f"<h2>{form['own_done']}</h2><p>You can close this page.</p>")


async def health(request: web.Request) -> web.Response:
    from pathlib import Path
    try:
        v = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
    except Exception:
        v = "?"
    return web.json_response({"status": "ok", "version": v})


def build_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/key", get_key),
        web.post("/key", post_key),
        web.get("/health", health),
    ])
    return app
