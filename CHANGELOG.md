# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2026-09-17 — 18+ fake accounts and phishing links only; shared AI key and AI switch (1.8.0)

### Fixed
- AI moderation was silently off for newly issued Gemini keys: `gemini-2.5-flash` returns 404 for them, so only the regex layer ran. The model is now the `GEMINI_MODEL` setting (default `gemini-3.1-flash-lite`).
- The bot could not reach a PostgreSQL addressed by a Docker service name — it forced `sslmode=require`. An explicit `sslmode` in `DATABASE_URL` now wins.
- Real members were muted as "profile bio looks like spam (advertisement)" for listing their own channel's invite link (`t.me/+…`) in their bio.

### Changed
- **The bot now blocks only 18+ fake accounts and phishing links.** Removed: the private invite-link and crypto-airdrop rules, the APK/EXE-in-bio ban, and the coordinated-burst ban (the same text from three accounts — identical greetings were enough). Admin-taught `/teach` keywords still apply.
- The AI prompt no longer assumes an IT community; bios linking the member's own channel and film discussion (age ratings included) are explicitly allowed.
- `/stats` and `/enable` say whether AI actually runs for a group, and why not (switched off vs no key).

### Added
- **Phishing links:** a link whose visible text is one site but opens another is deleted and its sender muted 24h, with no key or network call. With `VIRUSTOTAL_API_KEY`, each link's domain is checked with VirusTotal (acts at `VT_MALICIOUS_THRESHOLD`, default 2 engines).
- **`/globalkey`** (operator): one shared Gemini key for every group without its own; a group's own key always wins.
- **`/ai`** (operator): turn AI on/off for all groups at once or one by one; groups added later follow the default.
- **`OPERATOR_ALERTS=1`:** every ban and mute is mirrored to the operator's DM, naming the group and the account.
- **Docker deployment:** `Dockerfile`, `docker-compose.yml` and `deploy/` (see `deploy/README.md`).

## 2026-07-07 — Plain-language feedback buttons (1.7.2)

### Changed
- The DM feedback buttons no longer use the jargon "False positive / False negative". They now read "🚩 Not spam (wrongly flagged)" and "🐛 This IS spam (you missed it)", and the confirmation text matches. So when you forward spam the bot missed, you tap "This IS spam". Logic/callbacks unchanged.

## 2026-07-04 — Stop muting users over ambiguous profile photos (1.7.1)

### Fixed
- An uncertain NudeNet verdict (score in the 0.4–0.6 band) produced "profile photo ambiguous — needs admin review", which then muted the user 24h. Legitimate members were getting blocked over borderline photos. Ambiguous photos now take **no action** — only a clearly-explicit verdict (≥ 0.6) acts, and that one bans + deletes. Applies to both the join scan and the first-message scan.

## 2026-07-03 — Refocus moderation on explicit/nude/flirting, stop over-blocking (1.7.0)

### Changed
- **Detection scope narrowed to reduce false positives.** The bot was muting/banning legitimate users over harmless messages. It now focuses on: explicit/adult content, nude profile photos, and openly flirtatious come-ons, plus high-signal spam links (private `t.me/+` invites, crypto-airdrop scams).
- The AI layer now classifies only sexual/flirtatious content and is explicitly instructed to allow ads, insults, off-topic chatter, and friendly messages. It defaults to "not spam" on anything ambiguous.
- A single flagged message now gives a human a recoverable **24h mute** + admin alert, never an automatic permanent ban. Permanent bans stay reserved for severe profile hits (nudity / explicit-link / malware) and coordinated burst rings.

### Removed
- The broad `[ads]` keyword regex (Russian/Uzbek work/sale/discount/subscribe words) — it flagged normal conversation.
- The `[inappropriate]` insult keywords (ambiguous words like `mol` = "goods" caused false positives).
- The `[flirting]` keyword regex (`salom`, `qiz`, `sizga`, `yoqdi`, …) — everyday words that fed an automatic permanent-ban path.

## 2026-07-02 — Operator stats: which groups use the bot, spam caught per group (1.6.0)

### Added
- `/stats` (operator DM only): roster of every protected group with its name, enable date, and AI on/off, plus spam-removed and banned counts for yesterday / last 7 / last 30 days, broken down per group for yesterday.
- The morning operator report now leads with this activity summary before the token-cost report.
- `/enable` now refuses until the bot actually has admin rights (delete messages + ban users), instead of silently no-opping moderation.
- Abuse guard: a non-operator admin can protect at most `MAX_GROUPS_PER_OWNER` groups (default 20, env-overridable).

### Changed
- CI now runs the **full** test suite (`pytest`) on every push, not just two files — a regression anywhere now gates the deploy.
- `master` is now a protected branch (PR + passing CI required; admins can still push for emergency rollback).

## 2026-06-30 — Hard-ban nudity, explicit links, and malware on sight (1.5.0)

### Changed
- Nudity in a profile photo, a link to an explicit channel, or a malware/APK link are now **severe** signals: the account is **banned (kicked) and its message deleted**, not muted. These take priority over keyword matching. Ambiguous photos and generic spammy bios stay soft (24h mute + admin review) to avoid permabans on uncertain signals.
- The first-message scan now checks the **profile photo** as well as the bio, so link-joiners with a nude profile photo are caught on their first message (previously only the join-time scan checked photos). The scan still runs once per sender (cached); photos are only downloaded when the bio is clean.

## 2026-06-30 — Bio-flagged spam messages are now deleted (1.4.1)

### Fixed
- The first-message bio-scan path (1.4.0) muted the account and posted a "🚨 SPAM DETECTED — User blocked" alert but never deleted the offending message, so spam caught via the bio left its message in the group while keyword-caught messages were removed instantly. The bio path now deletes the message too, matching the text-detection path.

## 2026-06-29 — First-message bio scan catches link-joiners (1.4.0)

### Added
- Each sender's bio is now scanned on their **first message** in a protected group, not just at join. This closes the gap where accounts that join a public supergroup via invite link (which emits no `new_chat_members` event) were never profile-scanned — they could post a clean "Salom" while pushing a malware/explicit link from their bio. A hit mutes the account 24h pending review and alerts admins (Ban/Unmute). The check is bio-only (one `get_chat` call) and cached per (group, user) so it runs at most once per sender.

## 2026-06-29 — Token usage tracking, /tokens, and daily report (1.3.0)

### Added
- Per-group Gemini token accounting. Every classification call (message text and bios) records the model and token counts against the group whose BYOK key paid, so usage is attributable per owner.
- `/tokens` command — shows usage for the previous day, last 7 days, and last 30 days with model name, total tokens, and estimated cost in USD. Run inside a group (admins) for that group; run in the operator's DM for an all-groups breakdown.
- Daily usage report — every morning (~09:00 Asia/Tashkent, configurable via `REPORT_HOUR`) the operator gets an all-groups summary of the previous day, and each protected group's admins get their own group's numbers. Skips groups with no usage; guarded so a restart doesn't re-send.
- Cost estimates use configurable Gemini pricing (`GEMINI_PRICE_IN` / `GEMINI_PRICE_OUT`, default $0.30 / $2.50 per 1M tokens for gemini-2.5-flash).

### Changed
- 90-day data retention now also prunes old token-usage rows.

## 2026-06-27 — Auto-clean transient bot messages from groups (1.2.0)

### Added
- The bot now keeps groups tidy. Transient notices it posts — mute/ban announcements (`🔇 X was muted...`), report acknowledgements — auto-delete after 5 seconds.
- Admin commands and their replies are cleaned up: `/ban`, `/mute`, `/enable`, `/disable`, `/flag` (and their "not authorized" / usage / error replies) have the command message removed once handled, and the bot's reply removed 5 seconds later. Replies in private chats with the bot are never auto-deleted. (Requires the bot to have the "Delete messages" admin right, which it already needs for spam removal.)

## 2026-06-26 — Detect malicious links in profile bios (1.1.0)

### Added
- Profile scan now hard-flags accounts whose bio links a downloadable binary (`*.apk`, `*.exe`, `*.msi`, `*.dmg`, ...), including schemeless links like `best-app.apk`. This catches the "clean first message, malware payload in the bio" tactic where an account posts a harmless "Salom" but pushes a harmful download from its profile.
- Profile scan also hard-flags bios that pair a link with explicit/adult terms (bilingual UZ/RU/EN, plus 🔞 / `18+` / `onlyfans` / bare adult domains) — e.g. `🔞 t.me/xxx_channel`. Works with or without a group key. A link alone or explicit text alone won't trip it, so legit channel links stay safe.
- When a group has its own Gemini key (BYOK), the bio text is run through AI classification for spammy bios. Groups without a key still get the free malware-link + keyword detection.

### Changed
- Plain links, `t.me/` channels, and `@handles` in a bio are no longer auto-blocked — many legit users list their own channel or site. Those are now judged by the keyword/AI classifier instead of a blanket block, so legit accounts with channel info in their bio aren't muted.

### Known limitation
- Bio scanning still runs only at join time (added members and join-request approvals). Members who join a public supergroup via invite link are not yet scanned on their first message, so that path can still slip through until message-time scanning is added.

## 2026-06-23 — Stop routing stranger-group alerts to the operator (1.0.6)

### Fixed
- `notify_group` no longer falls back to the operator (`ADMIN_TELEGRAM_IDS`) when none of a group's own admins are reachable. Previously any group whose admins hadn't started the bot (e.g. a stranger who added the bot and ran `/enable`) dumped all its spam alerts on the operator. Now the alert is logged and dropped; a group gets DM alerts only once one of its own admins starts the bot. No tokens were ever charged for these groups — detection there is the free keyword layer (pure BYOK since 1.0.4 means no AI without the group's own key).

## 2026-06-22 — /setkey deep-link button when DM isn't open (1.0.5)

### Fixed
- `/setkey` no longer leaves an awkward "press Start" message in the group when the bot can't DM the admin. Flow now: if the admin has started the bot, the link goes straight to their DM (nothing in the group); if not, the bot posts ONE clean inline button ("🔑 Set up AI key (private)") that deep-links to the private chat, verifies the tapper administers that group, DMs the link, and deletes the group button. No token is ever exposed in the group.

## 2026-06-22 — Pure BYOK: drop the shared-key fallback (1.0.4)

### Changed
- Removed the operator-wide `GEMINI_API_KEY` fallback entirely. Every group — including the operator's own — uses only its own key set via `/setkey`. No key → AI off for that group (regex still runs). Simpler and uniform: the operator is never billed for anyone's group, and there's no special-casing by who enabled a group. `GEMINI_API_KEY` is no longer read; `KEY_ENCRYPTION_SECRET` is now what gates AI (it encrypts the per-group keys).

## 2026-06-22 — /setkey stays private in groups (1.0.3)

### Changed
- `/setkey` in a group now deletes the command message immediately and DMs the setup link privately, posting nothing public on success. This stops other members from seeing the command and spamming it; non-admin/copycat attempts are silently deleted. If the bot can't DM the admin (they haven't pressed Start), it posts one short nudge — never the link in public.

## 2026-06-22 — /setkey feedback + re-enable refreshes enabler (1.0.2)

### Fixed
- `/setkey` now replies in every case (run in a private chat, a non-enabled group, as an anonymous admin) instead of silently doing nothing.
- Re-running `/enable` now refreshes the group's recorded enabler. This lets an operator restore the shared-key fallback for their own channel (turned off by the 1.0.1 scoping when the group's enabler wasn't an operator) without re-entering a key — just run `/enable` again.

## 2026-06-22 — Scope the shared-key fallback to operator groups (1.0.1)

### Fixed
- The optional `GEMINI_API_KEY` fallback now applies **only to groups an operator enabled** (`enabled_by` ∈ `ADMIN_TELEGRAM_IDS`), not to every keyless group. Public groups must supply their own key via `/setkey` — the operator is never billed for a group they didn't set up. (Without this, the shared key silently subsidized every group that hadn't run `/setkey`.)

## 2026-06-22 — Public multi-tenant release (1.0.0)

The bot is now multi-tenant: anyone can add it to their own group, get keyword
protection instantly, and switch on AI moderation with their own Gemini key.

### Added
- **Per-group alert routing**: each group's moderation alerts now go to that group's own admins (the admin who ran `/enable` plus the live admin list), not a single global operator. The Ban/Unmute buttons authorize the group's admins.
- **BYOK (bring your own key)**: `/setkey` (group admin) DMs a one-time, 15-minute link to a web form where the admin pastes their Gemini key. The key is validated, encrypted at rest, and used only for that group. No key → keyword rules still run.
- **Per-group teaching**: `/teach` (reply to spam) learns keywords for that group; `/flag` (reply to a user) watchlists an account for that group. Operator DM teaching stays global (shared baseline).
- **Onboarding**: when added to a group the bot DMs the adder the setup steps.
- **`/privacy`** command and a 90-day auto-purge of stored spam-message text.
- **`GET /health`** endpoint (version + status).

### Changed
- `GEMINI_API_KEY` is now optional (an operator-wide fallback); per-group keys are preferred. The bot runs as a `web` process (serves the key-entry endpoint + polls in one process).

### Security
- Gemini keys encrypted at rest (Fernet, `KEY_ENCRYPTION_SECRET`); key-entry tokens stored only as SHA-256 hashes, single-use, short-TTL; the key form sends `no-referrer`/`no-store` and never echoes the key; key validation fails closed.

## 2026-06-22 — /mute reasons + group mute notices (0.16.0)

### Added
- `/mute` now takes an optional reason: `/mute <reason>` (24h), `/mute N <reason>` (N hours). `/mute` and `/mute N` still mute silently without a reason.
- When a user is muted — by `/mute` or by automatic spam detection — the bot posts a short notice in the group ("X was muted for N hours due to <reason>"). The reason is shown only when there is one.

## 2026-06-22 — Expanded /help (0.15.2)

### Changed
- `/help` now documents the full feature set: coordinated-spam handling, image-caption detection, profile scanning (bio + all photos), the admin DM tools (report false positive/negative, flag a suspicious account, teach keywords, `/feedback`), and release notes. Bilingual (Uzbek + English).

## 2026-06-22 — Render release notes as HTML (0.15.1)

### Fixed
- Release-note DMs are now sent as Telegram HTML instead of raw markdown, which rendered literally (`##`, `- `). Changelog headings become bold, list items become bullets, and `**bold**`/`` `code` `` are converted.

## 2026-06-22 — Release notes to admins (0.15.0)

### Added
- On every new release, the bot DMs the latest changelog section to bot admins and the admins of every protected group. Sent once per version (tracked in a new `app_state` table), so restarts on the same release don't re-send. Delivery is best-effort: a DM only reaches admins who have started the bot.

## 2026-06-22 — Scan all profile photos (0.14.1)

### Changed
- Profile photo scanning on join now checks all of a member's profile photos (up to 10), not just the most recent one. Counters the tactic of a clean first photo hiding explicit images behind it. The first explicit photo flags the account; otherwise any ambiguous photo still routes to admin review.

## 2026-06-22 — Flag suspicious accounts + photo feedback (0.14.0)

### Added
- The feedback flow now accepts forwarded **photos** (uses the caption), not just text.
- New **"Flag account"** action: forward a message from a bot account that posts benign text but whose profile pushes spam/explicit content, and flag the *sender's profile* instead of the message. The account is recorded (with a re-run of the bio/photo profile check) and watchlisted.
- Watchlisted accounts are never auto-banned. When one posts in a protected group, the bot alerts admins with Ban/Unmute buttons to decide (rate-limited to once per hour per account).

## 2026-06-22 — Admin misclassification feedback (0.13.0)

### Added
- Admins can forward any message to the bot in DM and flag it as a **false positive** (wrongly flagged) or **false negative** (missed spam), with an optional free-text note. Reports are stored for prompt/pattern tuning and reviewable with `/feedback`. The keyword-teaching flow is still reachable via a "Teach keywords" button on the same prompt.

### Fixed
- sqlite connections no longer get a bogus `sslmode=require` argument (it's added only for genuinely remote Postgres hosts), so the test suite can run against an in-memory database.

## 2026-06-21 — Fix meta-discussion false positive (0.12.1)

### Fixed
- AI moderation no longer flags messages that merely talk *about* channels, bots, spam, or the filter itself as advertisement. Only messages that actually push a specific channel/group (link or join/subscribe CTA) count as ads now.

## 2026-06-20 — Coordinated-spam burst detection (0.12.0)

### Added
- Coordinated-spam detection: when the same message is sent from 3+ different accounts within 2 minutes, the bot deletes every copy and bans all the accounts at once (one admin alert instead of ten). Catches multi-account floods even when the individual message text isn't a known spam pattern.

## 2026-06-20 — Crypto airdrop spam (0.11.2)

### Added
- Regex patterns for English crypto "free drop"/airdrop/giveaway scams (e.g. image caption "Free Solana Case Drop"), so they're caught for free without relying on the Gemini layer.

## [0.1.0] - 2026-04-05

### Added
- Initial implementation of minimal spam protection bot
- Advertisement detection using regex patterns and AI
- Inappropriate content filtering with regex and AI
- Differentiated blocking strategies (24h for humans, permanent for bots)
- Admin notification system for spam detections
- Manual override capability for admin
- `/ban` command for manual spam flagging
- Database logging for blocked users and spam reports
- Telegram bot framework (aiogram 3.13)
- PostgreSQL database integration (SQLAlchemy 2.0)
- Google Gemini AI integration for enhanced detection

### Changed
- Simplified architecture for focused spam protection
- Modular code structure for easier maintenance

### Fixed
- Proper error handling for AI API calls
- Database session management
- Message deletion safety checks

## [0.11.1] - 2026-06-20

### Added
- Also auto-removes the "X left the group" / "X was removed" service message (protected groups, needs delete permission).

## [0.11.0] - 2026-06-20

### Added
- Auto-removes the "X joined the group" service message when someone joins (in protected groups; requires the bot's delete permission).

## [0.10.7] - 2026-06-18

### Fixed
- **The bot no longer deletes/flags group admins' messages.** Admins are now exempt from moderation, checked against a per-group admin list cached for ~5 minutes (so it's not a per-message API call). An admin posting content that happens to match a pattern is left alone.

## [0.10.6] - 2026-06-18

### Fixed
- QA pass — edge-case crashes:
  - `handle_spam_detection` crashed on `from_user` being `None` (channel / linked-channel posts, anonymous senders). Those are now skipped — can't be moderated by user id anyway.
  - User-report handler crashed when the reporter was a channel-sender (`None`); now returns early.
  - `/mute` with a whitespace-only argument raised an uncaught `IndexError`; now handled.
  - Ban/Unmute button crashed if the alert was older than 48h (`cb.message` is `None`); now guarded.
- Hardened the keyword-teaching callback (`lp:`) with an explicit admin check.

## [0.10.5] - 2026-06-18

### Fixed
- **Security: any member could `/disable` (or `/enable`) protection.** The check verified whether the *bot owner* was an admin of the group (always true in the owner's group) rather than whether the *sender* was authorized, so any member's command succeeded. `/enable` and `/disable` now check the **sender's** group-admin status (consistent with `/ban` and `/mute`); regular members are rejected. Added a regression test (`tests/test_auth.py`).

## [0.10.4] - 2026-06-18

### Added
- CI: GitHub Actions workflow (`.github/workflows/ci.yml`) runs `py_compile`, the unit tests, and a smoke import on every push/PR to master — the gate for deploys (pair with Railway "Wait for CI").
- Dependabot (`.github/dependabot.yml`): weekly pip + github-actions update PRs, which run the same CI.

## [0.10.3] - 2026-06-18

### Removed
- Join-gate setup section removed from `/help`, `/start`, and the README. Join gating only applies to **private** groups that require approval to join; **public** groups (joinable via `@username`) generate no join requests, so the section was misleading. Public groups are protected by the on-join profile scan. The `chat_join_request` handler stays (dormant for public groups).

## [0.10.2] - 2026-06-18

### Fixed
- Corrected the join-gate setup instructions (were wrong): the bot needs the **"Invite Users via Link"** admin right (not "Add Members"), and join requests come from an **invite link with "Request Admin Approval"** (there is no "Approve New Members" members setting). Updated `/help` (re-translated), the README, accordingly.

## [0.10.1] - 2026-06-18

### Changed
- Documented the Guard-mode join gate: setup steps added to `/help` (re-translated) and the README, with a pointer from `/start`.

## [0.10.0] - 2026-06-18

### Added
- **Guard-mode join gate.** For groups that require join approval, the bot auto-vets each join request with the existing profile check (bio + photo) and **silently approves** clean profiles or **declines** spam ones — no captcha or button, zero friction for real users. Declines notify admins (with a "add manually if mistaken" note). Authorized groups only; non-protected groups are passed through.

### Changed
- Polling subscribes to `chat_join_request` updates via `resolve_used_update_types()`.

## [0.9.1] - 2026-06-17

### Fixed
- User reports no longer misfire on normal sentences that merely mention "ban"/"admin" (e.g. a question containing `/ban`). A report now requires the reply to be **just** a trigger word (`spam`, `ban`, `admin`, …) or `/report`. Also no longer reports the bot's own messages.

## [0.9.0] - 2026-06-17

### Added
- **`/ban` and `/mute`** for group admins — reply to a user's message. `/ban` removes the user and deletes the replied message; `/mute` mutes for 24h by default, or `/mute N` for N hours. Usable by the group's own admins (and the bot owner), anonymous admins included. Authorized groups only.

### Changed
- `/ban` is now a real moderation command (was a stub). `/help` and the command menu updated to reflect `/ban` + `/mute` and the reply-to-report tip.

## [0.8.0] - 2026-06-17

### Added
- **User reporting.** Any member can reply to a message with `spam`, `ban`, or `admin` (also `спам`/`бан`/`админ`/`жалоба`/`shikoyat`) to flag it. The bot DMs admins the reported message + reporter, with the same 🔨 Ban / ✅ Unmute buttons targeting the reported user. Rate-limited to 3 reports/min per reporter; authorized groups only. Non-report replies still flow to normal spam detection.

## [0.7.0] - 2026-06-17

### Added
- Inline **🔨 Ban / ✅ Unmute** buttons on admin alerts (both spam-detection and suspicious-profile-on-join). One tap bans the user (`ban_chat_member` — removes + blocks rejoin) or restores their permissions, straight from the DM. Buttons are admin-only.
- `BOTFATHER.md` — copy-paste BotFather profile setup (name, about, description, commands, privacy), bilingual.

## [0.6.3] - 2026-06-17

### Fixed
- `/enable` and `/disable` now work for **anonymous** group admins. Authorization checks the group's admin list (`get_chat_administrators` returns real user IDs even for anonymous posters) and allows the command if the bot owner is an admin of the group — no need to turn off "Remain Anonymous". Strangers are still blocked.

## [0.6.2] - 2026-06-17

### Fixed
- `/enable` and `/disable` now reply with a clear hint when the sender can't be verified — notably when posting **anonymously** as the group (Telegram replaces the real user with `GroupAnonymousBot`, hiding the admin's ID). Previously the command was silently ignored, which looked like the bot was broken.

## [0.6.1] - 2026-06-17

### Changed
- Simplified the onboarding/description copy to generic "spam and unwanted messages" wording and removed content-type specifics (the previous Uzbek read as vulgar). Re-translated via translate.py.

## [0.6.0] - 2026-06-17

### Added
- `/start` and `/help` commands with a bilingual (Uzbek + English) onboarding guide explaining what the bot does and how to set it up.
- Bot command menu and profile description set automatically at startup, localized (Uzbek default, English for `en` users) — no manual BotFather setup needed.

## [0.5.0] - 2026-06-17

### Added
- **Group allow-list.** The bot only moderates groups an admin authorizes with `/enable` (run inside the group); `/disable` removes it. Unauthorized groups get zero classification and zero Gemini calls — abuse/cost guard. Stored in the `allowed_groups` table (also the future home of per-group BYOK keys).

### Fixed
- ID columns widened to `BigInteger`. Telegram user IDs (>2.1e9) and supergroup IDs (~-1e12) overflow 32-bit `INTEGER`, which would have crashed the first real block/report. `init_db.py` migrates existing tables.

### Changed
- Router order: the join handler and admin commands now run before the broad group handler (which previously swallowed `/enable`, `/ban`, etc. in groups).

## [0.4.3] - 2026-06-17

### Changed
- Disabled `gemini-2.5-flash` thinking (`thinking_budget=0`) for classification. Benchmarked against real samples: ~2× faster (avg 1.4s → 0.7s on the model call) with identical 11/11 accuracy.

## [0.4.2] - 2026-06-17

### Changed
- Classifier now flags **flirtatious/seductive "teaser" one-liners** (provocative come-ons with no link or explicit word — e.g. "only real brave ones 💎", flirty openers to strangers) as adult spam. These spam-bot openers were previously judged clean because the prompt leaned benign for short link-less messages. Verified 11/11 against the live API on real samples.

## [0.4.1] - 2026-06-17

### Added
- Classification logging: every message logs `CLASSIFY result=… via=… text=…` (verdict, decision path, text snippet) so misclassifications are diagnosable from the logs.

## [0.4.0] - 2026-06-17

### Changed
- Replaced the two slow `gemini-2.5-pro` calls (ad + inappropriate) with a **single `gemini-2.5-flash` call** using one unified classifier. Cuts per-message latency from ~35–44s to a few seconds and halves API calls.
- Unified prompt now also detects **adult/sexual-content solicitation** (previously fell between the ad and insult classifiers and was missed) and explicitly de-obfuscates mixed Latin/Cyrillic, char-spacing, and broken grammar. Returns a `category`: advertisement / adult / inappropriate.

### Added
- `spam_bot/core/prompts.py` — classifier prompt, dependency-free so it's testable in isolation.
- `scripts/try_classify.py` — classify samples against the live API via `railway run`.

## [0.3.1] - 2026-06-17

### Fixed
- **AI moderation was silently disabled in production.** Code imports `google-genai` but `requirements.txt` pinned the wrong SDK (`google-generativeai`), so the import failed and only the regex layer ran — missing all obfuscated/mixed-script spam. Switched to `google-genai`; the import failure now logs loudly instead of swallowing.

### Changed
- Ad-detection prompt now explicitly de-obfuscates mixed Latin/Cyrillic, random characters, and broken grammar, and treats heavy obfuscation as a spam signal.
- Loosened Gemini rate limits (per-user 10/30s, global 120/min) so message bursts aren't silently passed as clean.

## [0.3.0] - 2026-06-17

### Added
- Startup notification: bot DMs admins `✅ spam-bot vX.Y.Z is up and running` on every boot (deploy/restart heartbeat)

## [0.2.0] - 2026-06-17

### Added
- Externalized spam patterns to editable `patterns/seed_patterns.txt` (no longer hardcoded)
- Admin teaching: forward spam in DM → bot replies with the spam/not-spam verdict, then offers keyword buttons → learned patterns saved to DB and applied live
- Seed patterns for `t.me/+` invite links and common Latin-script spam (zarabotok, skidka)
- `learned_patterns` table for admin-taught keywords
- Profile scanning on join: bio (regex/keyword) + profile photo via local NudeNet model; ambiguous photos routed to admins for review
- Cyrillic↔Latin homoglyph normalization to catch script-swap evasion
- Rate limiting on the paid Gemini layer (per-user + global fixed-window budget); regex layer always runs
- Pattern + rate-limit unit tests under `tests/`

### Changed
- Bot now runs as a module: `python -m spam_bot.main` (added package `__init__.py` files)
- Detection runs free regex/keyword layer first; Gemini called only when that layer is clean

### Fixed
- Syntax errors that prevented the bot from compiling (smart-quote prompts, apostrophe regex)