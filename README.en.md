<div align="center">

# 🛡️ Spam Protection Bot

**A self-serve Telegram bot that clears 18+ fake accounts and phishing links out of community groups — explicit profile photos and bios, adult spam-bot bait, and links that hide where they really go.**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Built for @ertagakech](https://img.shields.io/badge/built%20for-%40ertagakech-26A5E4?logo=telegram&logoColor=white)](https://t.me/ertagakech)

🇺🇿 [O‘zbekcha](README.md) · 🇬🇧 **English** · 🇷🇺 [Русский](README.ru.md)

</div>

> ### 🤖 Built for the [@ertagakech](https://t.me/ertagakech) Telegram channel
> This bot was created for **[@ertagakech](https://t.me/ertagakech)** — join the channel to learn more about AI, automation, and building things like this. 👉 **https://t.me/ertagakech**

## 🚀 Ready-to-use bot: [@spamliman_bot](https://t.me/spamliman_bot)

Don't want to host it yourself? **[@spamliman_bot](https://t.me/spamliman_bot)** ("Spam Fake Accounts") runs the code in this fork:

1. Add @spamliman_bot to your group and make it an **admin** with **Delete messages** + **Ban users**.
2. Send `/enable` in the group.
3. Open a private chat with the bot and press **Start**, so it can send you its alerts.

It removes 18+ fake accounts and phishing links, and leaves ordinary conversation, ads and channel links alone. AI moderation on this hosted bot is switched on by its operator.

---

## What it is

A Telegram moderation bot for community groups — IT learning, film discussion and more. Anyone can add it, run `/enable`, and get protection instantly. It is **multi-tenant**: each group can bring its own Google Gemini key (**BYOK**), and the operator can optionally provide one **shared key** for groups that have none. Without any key, the free checks — the local photo scan, explicit-link bios and disguised phishing links — still protect the group.

## 🎯 What gets blocked — and what doesn't

The bot acts on **two things only**:

| Blocked | How it's detected | Action |
|---|---|---|
| **18+ fake accounts** | clearly-explicit profile photo (NudeNet, runs locally) · a bio with a link next to explicit terms | ban + delete |
| | the AI judges a message or bio as sexual content or seductive spam-bot bait | delete + 24h mute |
| **Phishing links** | the link's visible text is one site but it opens another (`https://gov.uz/…` → `evil.cc`) | delete + 24h mute |
| | the link's domain is flagged as malicious by VirusTotal engines | delete + 24h mute |

**Not blocked:** ads and promotions, a member's own channel or invite link in their bio (`t.me/+…`), crypto talk, insults, off-topic chatter, film discussion including age ratings. Earlier versions muted people for some of these; those rules were removed.

A **24h mute** keeps the member in the group — they can read but not post — and lifts on its own. The group's admins (and the operator, with `OPERATOR_ALERTS=1`) get an alert with **Ban / Unmute** buttons, so a mistake is one tap to undo.

## ✨ Features

- **Multi-tenant, self-serve** — add the bot, `/enable` in the group, done. Each group's own admins receive its alerts.
- **18+ fake-account detection** — profile photos are checked locally with NudeNet (no cloud call) and ambiguous photos take no action. Bios and messages are judged by the AI layer, which is instructed to flag only sexual content and seductive spam-bot bait.
- **Phishing-link blocking** — disguised links are caught for free, with no network call. With a VirusTotal API key, each link's real domain (and its parent domain) is checked too. Only the domain is sent, verdicts are cached, and big platforms are never looked up.
- **AI keys: per group or shared** — `/setkey` stores a group's own Gemini key through a one-time web form, encrypted at rest. The operator can set one shared key for every group without its own (`/globalkey`); a group's own key always wins.
- **Operator AI switch** — `/ai` lists every group with its AI status and turns AI on or off for all groups at once or one by one. Groups added later follow the default.
- **Operator ban feed** — with `OPERATOR_ALERTS=1`, every ban and mute across all groups is mirrored to the operator's DM, naming the group, the account and the reason.
- **First-message + join scanning** — profiles are vetted when a member joins and on their first message, so link-joiners in public groups are covered too.
- **Admin tooling** — `/ban`, `/mute`, teach-keywords, flag-account and misclassification feedback, all from Telegram.
- **Usage & activity reporting** — `/tokens` shows Gemini token usage and cost; `/stats` shows the group roster, whether AI actually runs in each group, and the spam caught; the operator gets a morning report.
- **Tidy by design** — the bot's own notices and admin command messages auto-clean from the group after a few seconds.

## 🧠 How it works

Every message in a protected group runs through a cheap-to-expensive pipeline; the first hit wins:

1. **Profile scan (once per member)** — on join and on first message.
   - Clearly-explicit photo (NudeNet) or a bio linking explicit content → **ban + delete**.
   - Otherwise the bio goes to the AI layer (step 4); an 18+ verdict → 24h mute.
2. **Phishing-link check** — disguised links first (free), then VirusTotal domain reputation when a key is set. It runs before the AI, so a phishing post never costs a Gemini call.
3. **Keyword layer (free)** — only keywords a group's admins taught with `/teach`. The seed list blocks nothing on its own.
4. **AI layer** — runs when AI is switched on for the group (`/ai`) and a key is available: the group's own key, otherwise the operator's shared key. Gemini (`gemini-3.1-flash-lite` by default) judges only 18+ content. Rate-limited as a cost guard.

Everything is scoped per group, and the bot stays completely silent in groups that haven't run `/enable`.

**Privacy:** Gemini keys (per group and shared) are encrypted at rest with Fernet. Message text goes to Google Gemini only where AI is on. Link domains go to VirusTotal only when a key is set — never the message itself. Spam-report text and usage rows are purged after 90 days.

## 🛠️ Setup & deployment

The bot runs as a single long-polling worker plus a small web endpoint for the key-entry form. Two ways to host it:

- **Docker, any server** — `docker compose up -d --build` runs the bot on Python 3.11 with its own PostgreSQL. See [deploy/README.md](deploy/README.md).
- **Railway** — see [DEPLOY.md](DEPLOY.md).

### 1. Create the bot
In Telegram, talk to [@BotFather](https://t.me/BotFather): `/newbot`, then **disable privacy mode** (`/setprivacy` → Disable) so the bot can read group messages. Privacy mode is frozen per group at the moment the bot joins, so if you change it later, remove and re-add the bot.

### 2. Clone & install
```bash
git clone https://github.com/SarvarVakhobov/killspam-bot.git
cd killspam-bot
pip install -r requirements.txt
```

### 3. Configure environment
Copy `.env.example` to `.env` and fill it in:

| Variable | Required | What it is |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `ADMIN_TELEGRAM_IDS` | ✅ | Comma-separated operator IDs (system alerts, `/stats`, `/ai`, `/globalkey`) |
| `KEY_ENCRYPTION_SECRET` | ✅ | Fernet key encrypting stored Gemini keys. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Keep it stable — changing it makes stored keys unreadable |
| `BASE_URL` | ✅ | URL of the bot's web endpoint (builds the `/setkey` and `/globalkey set` links); must open for whoever uses them |
| `GEMINI_MODEL` | ➖ | Gemini model for AI moderation (default `gemini-3.1-flash-lite`). Change it when Google retires a model |
| `GEMINI_PRICE_IN` / `GEMINI_PRICE_OUT` | ➖ | $/1M tokens for `/tokens` cost estimates (default `0.30` / `2.50`, flash rates — set your model's real rates) |
| `OPERATOR_ALERTS` | ➖ | `1` mirrors every ban/mute to the operator's DM (default `0`) |
| `VIRUSTOTAL_API_KEY` | ➖ | Turns on VirusTotal link checks (free key: virustotal.com → profile → API key; 4 lookups/min, 500/day). The disguised-link check runs without it |
| `VT_MALICIOUS_THRESHOLD` | ➖ | How many engines must flag a domain before the bot acts (default `2`) |
| `REPORT_HOUR` | ➖ | Local hour (Asia/Tashkent) for the morning report (default `9`) |
| `MAX_GROUPS_PER_OWNER` | ➖ | Abuse guard: max groups one non-operator may `/enable` (default `20`) |

> ⚠️ Never commit your real `.env`. It is gitignored — keep it that way.

### 4. Deploy
With Docker, follow [deploy/README.md](deploy/README.md). On Railway, create a project, add a PostgreSQL plugin, set the variables above and deploy. Either way the start command (see `Procfile`) is:
```bash
python init_db.py && python -m spam_bot.main
```
`init_db.py` creates and migrates tables on every boot. Locally you can run the same two commands.

### 5. Protect a group
1. Add the bot to your group and make it an **admin** with **Delete messages** + **Ban users**.
2. Run `/enable` inside the group.
3. For AI, either run `/setkey` in the group (the group's own Gemini key), or — as the operator — send `/globalkey set` to the bot in a private chat to set a shared key.
4. As the operator, send `/ai` to choose which groups run AI.

> ⚠️ AI is **on by default** for every group. If you make your bot public with a shared key, groups added by strangers use that key too. Switch the default off in `/ai` and turn AI on only for the groups you choose.

### Rollback
Each release is a git tag (`vX.Y.Z`). To roll back, redeploy the previous tag; the DB schema is additive, so older code runs against a newer DB.

## 💬 Commands

| Command | Who | What |
|---|---|---|
| `/enable` · `/disable` | Group admins | Turn protection on/off for the group |
| `/setkey` | Group admins | Store the group's own Gemini key (private, one-time link) |
| `/ban` · `/mute` | Group admins | Moderate the replied-to user |
| `/tokens` | Group admins / operator | Gemini token usage + cost (yesterday / 7d / 30d) |
| `/stats` | Operator (DM) | Group roster with AI status + spam/ban activity |
| `/ai` | Operator (DM) | Turn AI on/off for all groups or group by group |
| `/globalkey` | Operator (DM) | Shared-key status; `set` to add one for keyless groups, `off` to remove it |
| `/help` · `/privacy` | Everyone | Usage guide / data policy |

## 🧰 Tech stack

Python 3.11 · [aiogram 3](https://docs.aiogram.dev/) · SQLAlchemy 2 + PostgreSQL · Google Gemini (`gemini-3.1-flash-lite`; per-group or shared key) · [NudeNet](https://github.com/notAI-tech/NudeNet) (local NSFW model) · [VirusTotal API v3](https://docs.virustotal.com/reference/overview) · aiohttp · Docker.

## 📄 License

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may use, modify, and share it freely for **any non-commercial purpose**. **Commercial use is not permitted.**

## 🙌 Credits

Created for the **[@ertagakech](https://t.me/ertagakech)** Telegram channel. Join to learn more about AI 👉 **https://t.me/ertagakech**
