# Deploy (Railway)

The bot runs as a **web** process: one process that long-polls Telegram AND
serves the key-entry endpoint (`/key`, `/health`) on `$PORT`. Railway runs the
`Procfile` `web:` process, which creates/migrates tables then starts polling +
the web server. Railway assigns it a public domain — set that as `BASE_URL`.

## First deploy

1. Install + log in to the Railway CLI:
   ```bash
   npm i -g @railway/cli   # or: brew install railway
   railway login
   ```
2. Create the project and add Postgres:
   ```bash
   railway init                 # create / link a project
   railway add --database postgres
   ```
3. Set environment variables (Dashboard → Variables, or CLI):
   ```bash
   # Generate the key-encryption secret (a Fernet key):
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

   railway variables --set BOT_TOKEN=... \
                      --set ADMIN_TELEGRAM_IDS=<your-telegram-id> \
                      --set DATABASE_URL='${{Postgres.DATABASE_URL}}' \
                      --set KEY_ENCRYPTION_SECRET=<the Fernet key above> \
                      --set BASE_URL='https://<your-app>.up.railway.app'
   ```
   - `DATABASE_URL` references the Postgres plugin's internal URL — no SSL needed
     (handled in `db/session.py`). External DB requiring SSL: append `?sslmode=require`.
   - `KEY_ENCRYPTION_SECRET` (required for BYOK) encrypts stored Gemini keys at rest.
     **Keep it stable** — rotating it makes existing stored keys undecryptable (groups must re-run `/setkey`).
   - `BASE_URL` is the bot's public Railway domain — used to build the `/setkey` link. Railway sets `$PORT` automatically.
   - Optionally the operator can set one shared Gemini key for every group without its own (`/globalkey set` in the bot's DM); a group's `/setkey` key always wins. Choose which groups run AI with `/ai`.
   - Optional variables — `GEMINI_MODEL`, `OPERATOR_ALERTS`, `VIRUSTOTAL_API_KEY`, `VT_MALICIOUS_THRESHOLD` — are described in the README's environment table.
4. Deploy the current directory:
   ```bash
   railway up
   ```
5. Watch logs: `railway logs` — expect "Database tables created successfully!"
   then "Starting minimal spam protection bot...".

`.env` is gitignored and not uploaded; all secrets live in Railway variables.

## Rollback

- **Where deploys live:** Railway Dashboard → service → **Deployments**.
- **Roll back:** open a previous green deployment → **Redeploy**. (CLI:
  `railway redeploy`.)
- **Most recent known-good version:** see `VERSION` (tag the commit when stable).
- Deploys are immutable snapshots, so rolling back is instant and safe.

## Post-deploy verification

- `GET https://<your-app>.up.railway.app/health` → `{"status":"ok","version":"..."}`.
- In a test group: `/enable` → `/setkey` → open the DMed link → paste a Gemini key →
  confirm "AI moderation is on". Send a spam message → it's removed and the group's
  admin gets the alert.

## Notes / deferred

- If you later connect a GitHub repo for auto-deploy, gate it on CI (don't let a
  raw push deploy unconditionally) and turn on branch protection + Dependabot.
- Key-entry tokens are delivered in the URL (mitigated by single-use + 15-min TTL +
  hashed-at-rest + `no-referrer`/`no-store`). Future hardening: move the token to a
  short-lived cookie + redirect so it never lands in logs/history.
