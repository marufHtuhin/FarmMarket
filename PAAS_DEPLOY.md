# FarmMarket — Deploy on Railway or Render (PaaS)

This guide deploys the production build (same image as the VPS stack) to a
platform-as-a-service. The app is one Docker service: the image builds the
React frontend and serves it from FastAPI, so there is no separate frontend
service to deploy.

**Honest status:** this path was prepared and config-verified (valid
`railway.json` / `render.yaml`, `$PORT` support, MySQL URL normalization,
health endpoint), but it has **never been deployed live to either platform
from here** — your first deploy is the live test. If a step fails, paste the
exact error (deploy log lines) to Muse.

## Which platform?

| | **Railway (recommended)** | **Render** |
|---|---|---|
| MySQL | Built in — add the MySQL template, one project | **No managed MySQL** (PostgreSQL only). You need an external MySQL 8 host (TiDB Cloud Starter is the recommended pick — see Render step 1; a Railway MySQL service also works) |
| Config in repo | `railway.json` (Dockerfile build + health check) | `render.yaml` (Blueprint: web service + disk) |
| TLS / domain | Automatic (`*.up.railway.app`, or your domain) | Automatic (`*.onrender.com`, or your domain) |
| Uploads | Attach a Volume at `/app/uploads` | Disk is in `render.yaml` (needs a paid plan) |
| Free tier | 30-day trial, one-time $5 credit (no card needed), then usage-based — the $5 should cover a hackathon demo; watch usage on the Railway dashboard, since the app and MySQL burn the same credit | Free web services exist but spin down after 15 min idle and cannot have a disk |

Both need the code in a GitHub repo first (Step 0). Prices change — check
the current pricing page of the platform you pick; the guide names no prices.

## Step 0 — Push the code to GitHub (both platforms)

Railway and Render deploy from git. From the extracted project folder:

```bash
git init
git add -A
git status        # MUST NOT list .env or *.db — .gitignore excludes them
git commit -m "FarmMarket production build"
git branch -M main
git remote add origin https://github.com/<you>/farmmarket.git
git push -u origin main
```

If `git status` shows `.env` or a `.db` file, stop — do not push secrets.
(`.gitignore` in the repo already excludes `.env`, `*.db`, `venv/`,
`node_modules/` and `frontend/dist/`; the Docker image rebuilds the
frontend, so `dist/` is not needed in git.)

## Railway (recommended path)

### 1. Create the project
- railway.com → **New Project** → **Deploy from GitHub repo** → pick the
  repo. Railway detects `railway.json`, builds `backend/Dockerfile`
  (repo-root context) and runs the container.
- The first build takes a few minutes (npm + pip). It will fail its health
  check until the database exists — that is expected; continue.

### 2. Add MySQL
- In the same project: **New** → **Database** → **Add MySQL**. Note the
  service name (default `MySQL`).
- Railway injects `MYSQL_URL` (private, in-project) and `MYSQL_PUBLIC_URL`.
  Use the **private** one for the app.

### 3. Set the API service variables
In the API service → **Variables**, add:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{MySQL.MYSQL_URL}}` (if your MySQL service is named differently, use `${{<Name>.MYSQL_URL}}`) |
| `SECRET_KEY` | A long random string (≥32 chars). Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENVIRONMENT` | `production` |
| `FRONTEND_ORIGINS` | `https://<your-app-domain>` (see step 4 — set after the domain exists) |
| `PUBLIC_BASE_URL` | `https://<your-app-domain>` (same) |
| `GEMINI_API_KEY` | (optional) your key — live Krishi Bondhu |
| `GEMINI_TIMEOUT_S` | `20` (raise to `45` if the assistant keeps timing out) |
| `OPENWEATHER_API_KEY` | **Legacy, ignored** — weather uses keyless Open-Meteo; do not set |
| `SCHEDULER_ENABLED` | `true` — enables the in-app daily price-freshness check (off by default; keep 1 replica — the scheduler runs in-process) |

Notes:
- `DATABASE_URL` as a Railway reference (`${{...}}`) stays correct even if
  Railway rotates credentials. The app normalizes the bare `mysql://`
  scheme to `mysql+pymysql://` and adds `charset=utf8mb4` automatically,
  so paste the reference exactly as shown.
- The app **refuses to start in production** with a demo/short `SECRET_KEY`,
  with `FRONTEND_ORIGINS=*`, or on SQLite. Those errors appear in the
  deploy log — fix the variable, Railway redeploys automatically.
- Never set `DATABASE_URL` to the public URL unless you must: the private
  URL is faster and is not exposed to the internet.

### 4. Generate the domain, then set the origins
- API service → **Settings** → **Networking** → **Generate Domain**. You get
  `https://<something>.up.railway.app` (or attach your own domain there).
- Now set `FRONTEND_ORIGINS` and `PUBLIC_BASE_URL` to exactly that URL
  (no trailing slash) and redeploy. Until `FRONTEND_ORIGINS` matches, the
  browser blocks API calls (CORS). Setting `PUBLIC_BASE_URL` pins the URL
  encoded in batch QR codes; if it is ever unset, QR codes fall back to the
  host of the request instead of a localhost default.

### 5. Attach a volume for uploads
- API service → **Volumes** (or Settings → Volumes) → add a volume,
  mount path `/app/uploads`. Size: **0.5 GB on the free trial** (the
  trial's volume cap — 1 GB will be rejected), **1 GB on Hobby or
  above**. 0.5 GB holds plenty of demo photos. Without a volume,
  uploaded listing photos disappear on every redeploy. (The app itself
  still works — only photos are affected.)

### 6. Deploy and verify
- Pushes to `main` redeploy automatically. Watch **Deployments** → logs:
  you should see Alembic migrations run, then uvicorn listening. The
  `railway.json` health check polls `/api/health` and only routes traffic
  once it returns 200.
- Open `https://<your-app-domain>/api/health` — expect `{"status": "ok",
  "project": "FARMMARKET", "db": "ok"}`. Then open the site, register, and log in.

### 7. First admin account (do NOT seed demo data)
Do not run `seed_demo.py` in production — it creates public demo accounts
(password `Demo123!`). The script refuses to run when
`ENVIRONMENT=production` unless passed `--allow-production`; still, simply
don't run it. Instead:
1. Register a normal account through the web UI.
2. In the Railway MySQL service, open its query console (or connect with
   the public URL from your machine) and run:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
SELECT id, email, role FROM users WHERE email = 'you@example.com';
```

3. Log out and back in (a new JWT is needed for the new role), then open
   the Admin dashboard. As admin you can also check
   `GET /api/v1/assistant/status` to see whether Gemini is live.

## Render path

### 1. Get an external MySQL 8 database first
Render has **no managed MySQL**. The recommended option is **TiDB Cloud
Starter** (permanent free tier, below); Railway MySQL is the alternative.
Copy the connection URL — you will paste it as `DATABASE_URL`.

#### TiDB Cloud Starter (recommended — permanent free, no $5/30-day clock)
TiDB is MySQL-compatible: 5 GiB row storage and 50M request units/month
on the free Starter tier, throttled (not billed) when you exceed them
without a spending limit. Unlike Railway it **requires a TLS
connection** — but the app handles that automatically: any
`*.tidbcloud.com` host gets verified TLS (certifi CA bundle; TiDB's
certificates come from Let's Encrypt, a publicly trusted CA) with no
extra variables, and migrations use the same settings.
1. tidbcloud.com → sign up → create a **Serverless (Starter)**
   cluster. Pick the region closest to Render (Render's default region
   is Oregon, so **AWS us-west-2** if offered) to keep latency low.
2. Create a database (e.g. `farmmarket`) and a user + password. TiDB
   usernames look like `xxxx.root` — copy the full username.
3. In the cluster's **Connect** dialog, set Connection Type **Public**
   and the **IP Access List to `0.0.0.0/0`** (allow all). Render has no
   static outbound IP, so a narrow allowlist will break the connection.
4. On Render, set `DATABASE_URL` to
   `mysql://<user>:<password>@<host>:4000/<database>` (port **4000**;
   bare `mysql://` is fine — the app normalizes it). **No `ssl`
   params in the URL and no extra env var are needed** — the app
   auto-detects `.tidbcloud.com` and enables verified TLS.
5. Deploy — Alembic migrations connect with the same TLS settings, so
   no extra step is needed there.

Warnings:
- **URL-encode special characters in the password** (`@`, `:`, `/`,
  `#`, `?`, `%`, …), or use a password without them — otherwise the
  URL parses wrong and the deploy fails at the health check.
- TiDB Starter closes idle connections after 5 minutes and may take a
  few seconds to wake — the app sets `pool_recycle=300` automatically
  for TiDB hosts. The first load after a pause can be slow.
- TiDB parses foreign-key DDL but historically does not enforce FKs —
  migrations should still apply; if the deploy log shows a migration
  error, that is the first suspect.

#### Alternative: Railway MySQL (simpler for a one-day demo)
Create a Railway project, add MySQL, enable public networking for it,
and copy its `MYSQL_PUBLIC_URL`. Any other MySQL 8 host works too —
paste its URL as `DATABASE_URL` (Railway MySQL needs no TLS settings).

Trade-off vs TiDB: Railway is still the simpler pick for a one-day
hackathon demo (no IP allowlist, no 5-minute idle shutdown), but the
trial is a one-time $5 credit for 30 days; TiDB never expires, so it is
the better pick if the app stays live after the hackathon.

### 2. Deploy from the Blueprint
- Render dashboard → **New +** → **Blueprint** → connect the GitHub repo.
  Render auto-detects `render.yaml` at the repo root.
- Fill in the prompted values:
  - `DATABASE_URL` — the external MySQL URL from step 1 (bare `mysql://`
    is fine; the app normalizes it).
  - `FRONTEND_ORIGINS` and `PUBLIC_BASE_URL` — use
    `https://farmmarket.onrender.com` for now, then correct them after the
    first deploy (see step 3).
  - `GEMINI_API_KEY` — optional; leave blank if
    you don't have a key yet. (Weather needs no key: Open-Meteo is keyless.)
  - `MAILJET_API_KEY` + `MAILJET_API_SECRET` — email for password reset
    + registration verification on Render **free** (see "Email setup"
    below). Render free blocks outbound SMTP ports (25/465/587), so
    Gmail SMTP cannot send mail from a free service — Mailjet (HTTPS)
    is the primary transport there; Postmark (`POSTMARK_SERVER_TOKEN`)
    and SendGrid (`SENDGRID_API_KEY`) are alternates. Precedence is
    Mailjet, then Postmark, then SendGrid, then SMTP. Optional, but
    without a mailer no emails are sent in production (the tokens are
    never in API responses there). The sender address (`SMTP_FROM` or
    `SMTP_USER`) must be verified with the provider in use.
  - `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — the SMTP
    fallback, for local dev (and paid Render plans, where SMTP ports
    are open). Gmail: host `smtp.gmail.com`, user = your Gmail address,
    password = a Gmail **app password** — Google Account → Security →
    2-Step Verification ON → App passwords → generate one for "Mail"
    (never the real Gmail password). `SMTP_PORT` (587) and
    `SMTP_USE_TLS` (true) are prefilled. Full note in
    `backend/.env.example`.
  - `SECRET_KEY` is generated by Render automatically.
- `render.yaml` uses the **starter** plan with a 1 GB disk at
  `/app/uploads`. The free plan cannot have a disk and spins down after
  15 minutes idle — if you switch to free, remove the `disk:` block from
  `render.yaml` first and accept that uploads vanish on redeploy.

### 3. Fix the origins to the real URL, then verify
- After the first deploy, Render shows the real URL (usually
  `https://farmmarket.onrender.com`, with a suffix if the name was taken).
  Update `FRONTEND_ORIGINS` and `PUBLIC_BASE_URL` to exactly that URL in
  **Environment** — Render redeploys on env change.
- Verify `https://<your-app-domain>/api/health`, then register and log in.
- First admin: same as Railway step 7, but run the `UPDATE users ...`
  SQL against your external MySQL host.

### 4. Email setup (Mailjet, Postmark, or SendGrid — Render free)

Render's free plan blocks outbound SMTP, so the deployed site sends mail
through an HTTPS email API instead. The mailer tries them in order —
Mailjet, then Postmark, then SendGrid, then SMTP — so SMTP can stay
configured for local dev without affecting the deployed site. Set only
one provider on Render (whichever you got working).

**Mailjet (primary — free 6,000/month, 200/day, no card, Gmail signup OK):**

1. **mailjet.com** → sign up for the free account → verify the account
   email Mailjet sends you.
2. **Account → Sender addresses** → add your Gmail address and verify it
   (Mailjet emails a confirmation link). **Sending fails until the
   sender address is verified** — this is the step most often missed.
3. **Account → API keys** → copy the **Master API key** and the
   **Secret key**. Never paste them in chat.
4. In Render, open the service → **Environment** → set `MAILJET_API_KEY`
   and `MAILJET_API_SECRET`, and make sure `SMTP_FROM` (or `SMTP_USER`)
   is exactly the Gmail address you verified in step 2. Save — Render
   redeploys on env change.
5. Test: register a new account on the live site → the confirmation
   email should arrive. If it doesn't, check the Render log for
   `Mailjet send failed` — the status + error name the cause (a
   non-"success" Status usually means the sender isn't verified yet).

**Postmark (alternative — free 100 emails/month, no card):** signup
requires a **work email** (a Gmail address doesn't qualify). If you have
one: create a Server → **API Tokens** → copy the Server token →
**Sender Signatures** → verify the Gmail sender address → set
`POSTMARK_SERVER_TOKEN` on Render (same `SMTP_FROM` rule as above).

**SendGrid (alternative — free 100 emails/day):** **Settings → Sender
Authentication → Verify a Single Sender** with the Gmail address →
confirm the verification email → **Settings → API Keys → Create API
Key** (Restricted Access → Mail Send → Full Access) → set
`SENDGRID_API_KEY` on Render. Note: SendGrid blocked one account at
login (ERR_USER_FORBIDDEN_ACCESS, an account-side block), so it is not
the primary path. The key is shown only once at creation.

## Frontend on Vercel + backend on Render (split hosting)

If the frontend lives on Vercel while the API stays on Render, the app
needs one extra piece: the frontend calls a **relative** `/api/v1` and
loads listing photos from relative `/uploads/...`, so on Vercel those
paths must be proxied to the Render backend. `frontend/vercel.json`
already does that (order matters: `/api` and `/uploads` first, SPA
fallback last). There is no code change and no CORS problem — the
browser only ever talks to the Vercel origin.

1. **Deploy the backend on Render first** (Render path above) and note
   its real URL (usually `https://farmmarket.onrender.com`, with a
   suffix if the name was taken).
2. **Fix `frontend/vercel.json`** if the Render URL differs: the two
   `destination` entries must point at your real Render backend URL.
   Push the change to GitHub.
3. **Vercel:** Import Project → the same GitHub repo → **Root
   Directory `frontend`** → Framework Preset **Vite** (build command
   `npm run build`, output directory `dist` — Vercel auto-detects both).
   No environment variables are needed for the frontend.
4. **Back on Render, set the origins to the Vercel URL** (Environment —
   Render redeploys on env change):
   - `FRONTEND_ORIGINS=https://<your-app>.vercel.app`
   - `PUBLIC_BASE_URL=https://<your-app>.vercel.app` — the QR code
     opens the verify page, which is a **frontend** route, so this must
     be the Vercel URL, not the Render URL. The password-reset and
     email-verification links use the same base, so they open the
     frontend too.
5. **Verify:** open the Vercel URL, register, log in, and check
   `https://<render-url>/api/health` returns
   `{"status": "ok", "project": "FARMMARKET", "db": "ok"}`.

Notes:
- The Render backend still builds and serves the frontend `dist` from
  its own URL too — harmless duplication; users should use the Vercel
  URL. The Render URL keeps working as a backup.
- The uploads disk on Render (starter plan) is still required — photos
  are stored by the backend, Vercel only proxies them.
- Render free services spin down after 15 min idle; the first load
  after idle takes ~30–50s. Starter stays warm.
- If the streaming (SSE) assistant chat ever feels delayed behind the
  Vercel proxy, the regular non-streaming chat still works — report it
  and the proxy behaviour can be revisited.

## Verify checklist (both platforms)

| Check | How | Success |
|---|---|---|
| Health + DB | `GET /api/health` | 200, `{"status": "ok", "project": "FARMMARKET", "db": "ok"}` |
| Site loads | Open the public URL | Marketplace with listings (empty until farmers list) |
| Auth works | Register + log in | Dashboard opens; refresh keeps you logged in |
| Gemini live? | Admin → `GET /api/v1/assistant/status` | `key_configured: true`, `last_gemini_error: null`, and a chat answer with `"mode": "gemini"` |
| Uploads persist | Upload a listing photo, redeploy, check it | Photo still there (volume/disk attached) |

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Build fails on `COPY frontend/...` | Build context is not the repo root. Railway: service root directory must be the repo root. Render: `dockerContext: .` is already in `render.yaml`. |
| Deploy stuck / health check fails | Database unreachable: check `DATABASE_URL` (Railway: is the `${{MySQL.MYSQL_URL}}` reference spelled with the right service name? Render: is the external MySQL reachable from the internet?). Read the deploy log — Alembic errors name the problem. |
| 502 Bad Gateway after deploy | App not listening on `$PORT`. This image reads `$PORT` (default 8000) — if you deployed an older zip, use the latest one. |
| CORS errors in the browser console | `FRONTEND_ORIGINS` must exactly equal the public URL (`https://...`, no trailing slash, no `*`). Fix the variable and redeploy. |
| "Refusing to start in production" in logs | `SECRET_KEY` missing/short/demo, or `DATABASE_URL` is SQLite. Fix the variables. |
| Photos disappear after redeploy | No volume/disk attached (Railway step 5 / Render disk in `render.yaml`). |
| Assistant always in template mode | Admin → `/api/v1/assistant/status`: `last_gemini_error` names the cause. Timeout → set `GEMINI_TIMEOUT_S=45` and redeploy. |
| `/logistics/optimize` returns 503 | OR-Tools missing from the image — deploy an older build? The current Dockerfile installs `requirements-ortools.txt`; redeploy from the latest zip. Locally: in the venv, from `backend/`, run `pip install -r requirements-ortools.txt`. |
| Render free service slow to wake | Free services spin down after 15 min idle; first load takes ~30–50s. Starter plan stays warm. |
| Weather page says "unavailable" on Render | Open-Meteo's free limits are counted per IP — Render's shared outbound IP can hit the daily limit (429) even though the API is healthy. The Weather page now falls back to fetching Open-Meteo directly from the visitor's browser, so it keeps working. The Render log line `Open-Meteo request failed` shows the server-side cause. |
| No emails arrive from the deployed site (Render free) | Render free blocks outbound SMTP ports (25/465/587), so Gmail SMTP cannot work on the free plan. Set a Mailjet/Postmark/SendGrid credential on Render (see "Email setup" above) — the mailer uses the HTTPS API instead. Check the Render log for `Mailjet send failed` / `Postmark send failed` / `SendGrid send failed` — the usual cause is a sender address that isn't verified with the provider yet. |
| Mail spam e gele | Gmail flags emails containing localhost links — the old `:5500` links were the trigger. On the deployed site the links use the real public URL, and mail is now sent as `FarmMarket <address>` via the HTTPS email API (Mailjet/Postmark/SendGrid), so inbox placement should be much better (no guarantee — Gmail decides). For the demo, mark one mail "Not spam" once and Gmail learns the sender. |

## What is intentionally NOT included

Same as `DEPLOY.md`: no payments, no identity verification, no dispute
resolution. Password-reset and registration-verification emails ARE
included — they need a mailer configured: a Mailjet/Postmark/SendGrid
credential on Render free (see "Email setup" above), or the `SMTP_*`
variables (Gmail app password) for local dev / paid plans. With no
mailer configured, no emails are sent. Backups are the database host's
job on PaaS (enable the MySQL provider's backups);
`scripts/backup-mysql.sh` is for the VPS stack.
