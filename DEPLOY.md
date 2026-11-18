# FarmMarket — Production Deployment Guide (VPS + Docker + Caddy)

Deploy the full stack — MySQL 8, FastAPI + React SPA, Caddy with automatic
HTTPS — on a single VPS. Read the whole guide before running anything.

> **Verification status — be honest about this.** The production files in
> this repo (`docker-compose.prod.yml`, `Caddyfile`, `scripts/backup-mysql.sh`,
> the non-root `Dockerfile` change) are **config-verified only**: the YAML
> parses, the shell script passes `bash -n`, and every setting was reviewed
> against the docs. They have **not** been built or run, because the build
> environment has no Docker, no MySQL, and no public domain. The first real
> deploy is also the first live test — follow the checks in each step and
> do not skip Step 6 (TLS). Likewise, seeded prices are **illustrative demo
> data**, not live market rates, and **no trained vision model ships**, so
> photo grading reports "model not trained" until you train one
> (see `LIMITATIONS.md`).

## Prerequisites

- A VPS (2 vCPU / 2 GB RAM minimum) running Ubuntu 22.04+ or Debian 12+,
  with Docker Engine + Docker Compose v2 installed and the `docker compose`
  command working. Verify: `docker compose version`.
- A domain name you control (e.g. `farmmarket.example.com`).
- SSH access to the VPS, and ports 80 + 443 open (firewall + cloud security
  group). Caddy needs port 80 reachable from the internet for the Let's
  Encrypt HTTP-01 challenge.
- The FarmMarket code (a git clone or the release zip).

## Step 1 — Point DNS at the VPS

Create an **A record** for your domain pointing at the VPS's public IPv4
address:

| Type | Name | Value |
|---|---|---|
| A | `farmmarket.example.com` (or `@` / a subdomain) | `<VPS public IP>` |

Wait for propagation before starting Caddy, or certificate issuance will
fail (Step 6). Check with:

```bash
dig +short farmmarket.example.com
# must print the VPS IP
```

## Step 2 — Get the code on the server and create the env file

```bash
# Option A: git
git clone <your-repo-url> /srv/farmmarket
cd /srv/farmmarket

# Option B: release zip
mkdir -p /srv/farmmarket && cd /srv/farmmarket
unzip FarmMarket.zip   # adjust the filename; the repo root contains docker-compose.prod.yml
```

**Environment file — one consistent approach.** The production stack reads
its variables from a **`.env` file in the repo root** (the same directory as
`docker-compose.prod.yml`). Compose reads the root `.env` for `${}`
substitution and passes the values into the containers; the backend does
**not** read a `.env` file inside the container (`.env` is excluded from
the Docker image by `.dockerignore`). Do not create `backend/.env` for the
production Docker deploy — it would be ignored.

```bash
cp backend/.env.example .env
```

## Step 3 — Set the required environment variables

Edit the root `.env` and set these four **required** variables (compose
fails fast with a clear error if any is missing — there are no defaults
and no default passwords anywhere in the production files):

```dotenv
# The public domain Caddy serves and obtains a TLS certificate for.
DOMAIN=farmmarket.example.com

# JWT signing key: >= 32 random characters, never a demo value. Generate:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<paste the generated value here>

# MySQL root password. Use URL-safe characters only (letters, digits, - _ .)
# or percent-encode special characters: the password is embedded in
# DATABASE_URL, which compose builds from this variable. Generate:
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
MYSQL_ROOT_PASSWORD=<paste a long random password here>

# The single public origin allowed to call the API cross-origin.
FRONTEND_ORIGINS=https://farmmarket.example.com
```

`DATABASE_URL` is **not** set by hand in production: compose builds it from
`MYSQL_ROOT_PASSWORD` (`mysql+pymysql://root:<password>@db:3306/farmmarket_db`).
The dev-only `DATABASE_URL` line already in `.env.example` is ignored by the
production compose file.

**Optional variables** (empty = clearly-labelled fallback mode):

```dotenv
HUB_PROFILE=bangladesh          # or sub_saharan
GEMINI_API_KEY=                 # Krishi Bondhu assistant (Google AI Studio, free)
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TIMEOUT_S=20             # Gemini call timeout (seconds; min 5). Raise it
                                # only if the assistant falls back to template mode
                                # with timeout errors — check the admin-only
                                # GET /api/v1/assistant/status first; it shows
                                # the last Gemini error and when it happened.
                                # (Weather needs no key: Open-Meteo is keyless.
                                # OPENWEATHER_API_KEY is legacy and ignored.)
OSRM_BASE_URL=                  # self-hosted OSRM server for road routing
SCHEDULER_ENABLED=true          # in-app daily price-freshness check (off by
                                # default; keep the api service at 1 replica)
```

`PUBLIC_BASE_URL` is set automatically to `https://<DOMAIN>` (it is the base
URL encoded in Digital Twin batch QR codes).

**Never** put real secrets in git. `.env` is gitignored — keep it that way,
and back up the file itself somewhere safe (losing `SECRET_KEY` invalidates
every issued JWT; losing `MYSQL_ROOT_PASSWORD` locks you out of the database
container).

## Step 4 — Start the stack and check health

```bash
cd /srv/farmmarket
docker compose -f docker-compose.prod.yml up -d --build
```

This builds the image (node builds the React SPA, python serves it),
starts MySQL, waits for it to be healthy, then starts the API — which runs
`alembic upgrade head` before serving — and finally Caddy.

Check the stack:

```bash
docker compose -f docker-compose.prod.yml ps
# db, api and caddy should all show "(healthy)" / "Up"

docker compose -f docker-compose.prod.yml logs -f api
# look for "Uvicorn running on http://0.0.0.0:8000" and no tracebacks

curl -s https://farmmarket.example.com/api/health
# expect HTTP 200. HTTP 503 means the API is up but cannot reach MySQL —
# check `docker compose -f docker-compose.prod.yml logs db`.
```

Then open `https://farmmarket.example.com` in a browser: the React app loads
from the same origin as the API. Only Caddy is exposed to the host
(ports 80/443); the API (port 8000) and MySQL (port 3306) are reachable
only inside the compose network.

## Step 5 — First admin account (do NOT seed demo data)

**Do not run the demo seed in production.** `python seed_demo.py` creates
12 public demo accounts (all with the published password `Demo123!`,
including `admin@farmmarket.demo`) plus illustrative demo listings and
synthetic price history. The script refuses to run when
`ENVIRONMENT=production` unless passed `--allow-production` — but don't
pass it on a production database. (If you want a demo, run the seed only
on a throwaway staging instance, never on the production database.)

Instead, create the first admin by hand:

1. Register a normal account through the web UI (any role — farmer is fine).
2. Promote it to admin from the VPS:

```bash
docker compose -f docker-compose.prod.yml exec db mysql -uroot -p farmmarket_db
-- (enter MYSQL_ROOT_PASSWORD when prompted, then at the mysql> prompt:)
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
SELECT id, email, role FROM users WHERE email = 'you@example.com';
-- expect: role = admin. Then type: exit
```

3. Log out and back in (a new JWT is needed for the new role), then open
   the Admin dashboard.

## Step 6 — TLS (automatic via Caddy)

Caddy obtains and renews a Let's Encrypt certificate automatically as soon
as it can serve the domain over HTTP — there is no manual certificate
configuration. Verify:

```bash
curl -I https://farmmarket.example.com
# expect: HTTP/2 200 and a Strict-Transport-Security header
```

Also confirm in a browser that the padlock shows a valid certificate and
that `http://farmmarket.example.com` redirects to `https://`.

**If HTTPS fails**, check in this order:

1. DNS: `dig +short farmmarket.example.com` must return the VPS IP.
2. Ports: port 80 must be open from the internet (`sudo ufw allow 80,443/tcp`
   on Ubuntu, plus any cloud security-group rule). The HTTP-01 challenge
   cannot complete otherwise.
3. Caddy logs: `docker compose -f docker-compose.prod.yml logs caddy` —
   look for ACME errors (rate limits, DNS failures, challenge timeouts).
4. If the domain is new, wait a few minutes for DNS propagation, then
   restart Caddy: `docker compose -f docker-compose.prod.yml restart caddy`.

## Step 7 — Backups

The repo ships `scripts/backup-mysql.sh`: it dumps the production database
with `mysqldump` (run inside the `db` container, so the script never reads
or prints the password), writes a timestamped `.sql.gz` file to `./backups/`,
and deletes dumps older than 7 days. Safe to run repeatedly.

```bash
./scripts/backup-mysql.sh
ls -lh backups/
```

Schedule it daily with cron (adjust the path to your checkout):

```cron
0 3 * * * cd /srv/farmmarket && ./scripts/backup-mysql.sh >> backups/backup.log 2>&1
```

Restore (mysqldump output drops each table before recreating it, so this
overwrites the current database — use with care):

```bash
gunzip -c backups/farmmarket-<timestamp>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" farmmarket_db'
```

Also back up the `uploads_data` volume (user-uploaded listing photos) and
the root `.env` file — the database dump contains neither. A simple option:

```bash
docker run --rm -v farmmarket_uploads_data:/data -v /srv/farmmarket/backups:/backup \
  alpine tar czf /backup/uploads-$(date +%Y%m%d).tar.gz -C /data .
# (volume name is prefixed with the compose project name — confirm with `docker volume ls`)
```

## Step 8 — Updating and rolling back

**Update** (after testing the new version on staging first):

```bash
cd /srv/farmmarket
git pull            # or unzip the new release over the checkout (keep .env and backups/)
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api   # watch the migration + startup
```

The API container runs `alembic upgrade head` on every start, so schema
migrations apply automatically. Uploaded photos and the database live in
named volumes and survive rebuilds.

**Rollback:**

```bash
git revert <bad-commit>        # or: git checkout <previous-tag>
docker compose -f docker-compose.prod.yml up -d --build
```

**Warning — migrations are one-way.** Rolling back code does not roll back
the database. If the bad release ran a migration, downgrade explicitly —
and only after a backup (Step 7):

```bash
./scripts/backup-mysql.sh
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1
```

## PaaS notes (Railway / Render-style platforms)

The Caddy + `docker-compose.prod.yml` setup above is for a **VPS**. On a
PaaS you do not use either file — see **`PAAS_DEPLOY.md`** for the full
guide (Railway first, Render second). The short version:

- Deploy from the **Dockerfile** (`backend/Dockerfile`, build context =
  repo root). The platform builds the image; the container listens on the
  platform-injected `$PORT` (default 8000) and TLS is provided by the
  platform. `railway.json` and `render.yaml` are in the repo root.
- Attach a **MySQL 8 database** and set `DATABASE_URL` to its connection
  string. Railway has managed MySQL built in; **Render has no managed
  MySQL**, so Render needs an external MySQL host. Bare `mysql://` URLs
  are normalized automatically (`mysql+pymysql://` + `charset=utf8mb4`).
- Set the same env vars as Step 3 in the platform dashboard:
  `SECRET_KEY`, `ENVIRONMENT=production`,
  `FRONTEND_ORIGINS=https://<your-paas-domain>`,
  `PUBLIC_BASE_URL=https://<your-paas-domain>`, plus the optional
  `GEMINI_API_KEY`.
- **Uploads need a persistent disk.** Uploaded photos live in
  `/app/uploads` inside the container; without a persistent volume mounted
  there, a redeploy deletes them. Mount the platform's persistent disk at
  `/app/uploads` (or set `UPLOAD_DIR` to the disk's mount path).
- Backups are the platform's job for managed MySQL (enable its backup /
  point-in-time recovery); `scripts/backup-mysql.sh` is for the VPS stack.

## What is intentionally NOT included

- **Payments** — no payment provider is integrated. Confirm payment details
  with the other party before any real-world transaction.
- **Identity verification** — accounts are self-registered; there is no
  KYC, phone verification, or farmer-identity check.
- **Dispute resolution** — no dispute, refund, or arbitration flow exists.
- **Password-reset email delivery** — a mailer exists (`app/services/mailer.py`,
  stdlib SMTP) and sends reset + registration-confirmation emails, but it
  needs the `SMTP_*` variables configured (see `.env.example` — Gmail with
  an app password works). Without SMTP configured, registration + password
  reset still work but no emails are sent; in production the reset link is
  only delivered by email, so set SMTP up before going live. An admin can
  still reset a user's password by direct database intervention (update the
  user's `password_hash` — generate it with
  `python -c "from app.security import hash_password; print(hash_password('NewPass123!'))"`
  run inside the api container).
- **Trained vision model** — photo grading returns "model not trained"
  until you train one (see `LIMITATIONS.md`). No grading accuracy is
  claimed.
- **Live market prices** — there is no live Bangladesh price feed. Any
  seeded prices are illustrative demo data; load verified observations
  before presenting prices as real.
