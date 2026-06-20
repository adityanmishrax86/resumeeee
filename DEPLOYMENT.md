# Deployment Guide — AI Job Copilot

This guide covers deploying the three components of the project to a real environment:

1. **Backend** — FastAPI service (`backend/app`) + PostgreSQL
2. **Frontend** — Vite-built static SPA (`frontend/`)
3. **Chrome extension** — Manifest V3 extension (`extension/`)

> The project today is wired for local development. This document highlights every place where a production deploy differs from `npm run dev` / `uvicorn --reload`, and gives copy-pasteable artifacts (Dockerfiles, systemd unit, Nginx config, etc.).

---

## 1. Topology

```
┌───────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│ Chrome Extension  │─────▶│   Frontend SPA   │─────▶│ FastAPI Backend    │
│  (per user)       │      │  (static files)  │ HTTPS│  (uvicorn+gunicorn)│
└───────────────────┘      └──────────────────┘      └─────────┬──────────┘
                                                               │
                                                               ▼
                                                       ┌────────────────┐
                                                       │  PostgreSQL    │
                                                       └────────────────┘
```

The extension is distributed **per-user** (Chrome Web Store or "Load unpacked"). The frontend and backend are deployed once per environment.

**Hosts you will need URLs for:**

| Component | Example production URL |
|---|---|
| Backend API | `https://api.jobcopilot.example.com` |
| Frontend SPA | `https://app.jobcopilot.example.com` |
| Postgres | managed service (RDS, Neon, Supabase, Railway, etc.) |

---

## 2. Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 14+ |
| `psql` CLI | matching server version |
| Docker | 24+ (optional, for container deploy) |
| Chrome | 114+ (for the extension) |

At least one LLM API key:
- `GOOGLE_API_KEY` — **required** if you want the `interview_research` agent (it uses Gemini + web search)
- `NVIDIA_API_KEY` — for NVIDIA NIM / Nemotron
- `ANTHROPIC_API_KEY` — for Claude
- `COHERE_API_KEY` — for Cohere
- or `LLM_PROVIDER=mock` for a no-cost deterministic mode

---

## 3. Environment variables

All backend config is read from environment variables. In development the backend loads them from [backend/app/.env](backend/app/.env); in production set them on the host / container / PaaS dashboard.

### Required

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Full SQLAlchemy URL. Must use the **`psycopg`** (psycopg3) driver, e.g. `postgresql+psycopg://user:pw@host:5432/jobcopilot` |
| `LLM_PROVIDER` | `google` \| `nvidia` \| `anthropic` \| `cohere` \| `mock` |

### Per-provider keys (set the one matching `LLM_PROVIDER`)

| Variable | Used by |
|---|---|
| `GOOGLE_API_KEY` + `GOOGLE_LLM_MODEL` (default `gemini-2.5-flash-preview`) | Google client |
| `NVIDIA_API_KEY` + `NIM_MODEL` + `NIM_INVOKE_URL` | NVIDIA NIM client |
| `ANTHROPIC_API_KEY` | Claude |
| `COHERE_API_KEY` | Cohere |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root logger level |
| `APP_ENV` | `dev` | Tagged in Logfire spans (`prod`, `staging`, …) |
| `APP_VERSION` | `0.1.0` | Service version reported to Logfire |
| `OTEL_SERVICE_NAME` | `ai-job-copilot-backend` | OTEL service name |
| `LOGFIRE_TOKEN` | — | Enable Logfire ingestion |
| `SENTRY_DSN` | — | Enable Sentry SDK |

### Two ways to deliver LLM credentials

The backend supports **either** of:

1. **Env-driven** — bake `LLM_PROVIDER` + the matching API key into the environment. Simpler for stateless containers.
2. **DB-driven** — leave env empty and let an operator configure the provider through the in-app **Setup** screen. The Settings Service encrypts the key at rest (Fernet) using a per-instance master key file at `backend/app/.secret_key` and rehydrates `os.environ` on startup.

> ⚠️ **If you use DB-driven settings, you MUST persist `backend/app/.secret_key` across restarts** (mount it as a volume or store it in a secret manager). Lose the file and the encrypted API key in the DB becomes unreadable.

---

## 4. Database setup

The codebase uses SQLAlchemy ORM but does **not** auto-create the full schema on startup (only the `app_settings` table is auto-created). The other tables are managed by hand-written SQL migrations in [backend/app/db/migrations/](backend/app/db/migrations/).

Apply them in order against your target DB:

```bash
cd backend/app/db/migrations

# Run on a fresh database
for f in 0001 0002 0003 0004 0005 0006 0007 0008 0009 0010; do
  psql "$DATABASE_URL_PSQL" -v ON_ERROR_STOP=1 -f ${f}_*.sql
done
```

> `DATABASE_URL_PSQL` is the same connection string without the `+psycopg` SQLAlchemy prefix, e.g. `postgresql://user:pw@host:5432/jobcopilot`.

For a managed Postgres provider:

- Create a database and a role with `CONNECT`, `CREATE`, `USAGE`, and full DML grants on the public schema.
- Whitelist the backend host's outbound IP (or attach it to the provider's private network).
- Use TLS — append `?sslmode=require` to `DATABASE_URL`.

---

## 5. Backend deployment

The ASGI entrypoint is `app.main:app`. Pin the working directory to `backend/` so the `app` package import works.

### 5.1 Recommended process model

Use **gunicorn** as a supervisor with **uvicorn workers**:

```bash
pip install gunicorn
gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 360 \
  --graceful-timeout 30
```

- Worker count: start with `2 × vCPU + 1`, then tune.
- `--timeout 360` matches the frontend's 330 s `postJson` timeout (see [frontend/api.js](frontend/api.js#L17)). Long-running orchestrations should run in the background but per-request endpoints can still take >60 s with LLM calls.
- Keep `--workers` modest if you use the in-process orchestrator (`background=true`), because each worker holds its own thread pool.

### 5.2 Option A — Docker

Create [backend/Dockerfile](backend/Dockerfile):

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# System deps for psycopg + cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /srv/app/requirements.txt
RUN pip install -r /srv/app/requirements.txt gunicorn

COPY app /srv/app

# Persisted across restarts via a volume mounted at /srv/app/.secret_key
VOLUME ["/srv/app"]

EXPOSE 8000

CMD ["gunicorn", "app.main:app", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "360"]
```

Build and run:

```bash
cd backend
docker build -t jobcopilot-backend:latest .
docker run -d --name jobcopilot-backend \
  -p 8000:8000 \
  -e DATABASE_URL='postgresql+psycopg://user:pw@db:5432/jobcopilot' \
  -e LLM_PROVIDER=google \
  -e GOOGLE_API_KEY='...' \
  -e APP_ENV=prod \
  -v jobcopilot_secret:/srv/app \
  jobcopilot-backend:latest
```

A minimal **docker-compose.yml** for a single-host deploy:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: jobcopilot
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: jobcopilot
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U jobcopilot"]
      interval: 5s
      retries: 10

  backend:
    build: ./backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+psycopg://jobcopilot:changeme@db:5432/jobcopilot
      LLM_PROVIDER: ${LLM_PROVIDER}
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      APP_ENV: prod
    volumes:
      - backend_secret:/srv/app
    ports:
      - "8000:8000"

volumes:
  pgdata:
  backend_secret:
```

After the first start, run the SQL migrations once:

```bash
docker compose exec db psql -U jobcopilot -d jobcopilot \
  -f /docker-entrypoint-initdb.d/0001_create_app_settings.sql   # repeat for 0002–0010
```

(or mount `backend/app/db/migrations/` into the `db` container's `/docker-entrypoint-initdb.d/` so they run on first boot).

### 5.3 Option B — VM with systemd

On an Ubuntu/Debian host:

```bash
sudo apt install -y python3.11 python3.11-venv libpq-dev build-essential
sudo useradd -r -m -d /opt/jobcopilot jobcopilot
sudo -u jobcopilot git clone <your-repo> /opt/jobcopilot/src
cd /opt/jobcopilot/src/backend
sudo -u jobcopilot python3.11 -m venv .venv
sudo -u jobcopilot .venv/bin/pip install -r app/requirements.txt gunicorn
```

Drop secrets into `/etc/jobcopilot.env` (mode `0600`, owned by `jobcopilot`):

```env
DATABASE_URL=postgresql+psycopg://...
LLM_PROVIDER=google
GOOGLE_API_KEY=...
APP_ENV=prod
LOG_LEVEL=INFO
```

Create `/etc/systemd/system/jobcopilot-backend.service`:

```ini
[Unit]
Description=AI Job Copilot backend
After=network.target

[Service]
Type=simple
User=jobcopilot
WorkingDirectory=/opt/jobcopilot/src/backend
EnvironmentFile=/etc/jobcopilot.env
ExecStart=/opt/jobcopilot/src/backend/.venv/bin/gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --timeout 360
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jobcopilot-backend
sudo journalctl -u jobcopilot-backend -f
```

Front it with Nginx (TLS terminator):

```nginx
server {
  listen 443 ssl http2;
  server_name api.jobcopilot.example.com;

  ssl_certificate     /etc/letsencrypt/live/api.jobcopilot.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.jobcopilot.example.com/privkey.pem;

  client_max_body_size 5m;

  location / {
    proxy_pass         http://127.0.0.1:8000;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 360s;
    proxy_send_timeout 360s;
  }
}
```

### 5.4 Option C — PaaS

The image / process is plain Python + ASGI, so any PaaS works:

| Provider | Notes |
|---|---|
| **Render** | Web Service → Runtime `Python 3.11` → Build `pip install -r app/requirements.txt gunicorn` → Start `gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --timeout 360`. Add a Render Postgres add-on for `DATABASE_URL`. Add a **Persistent Disk** mounted at `/opt/render/project/src/backend/app` to keep `.secret_key`. |
| **Railway** | Same start command; use the Postgres plugin. Mount a volume for `.secret_key` or supply credentials via env only. |
| **Fly.io** | `fly launch` from `backend/`, add `[mounts]` for `.secret_key`, attach Fly Postgres. |
| **AWS ECS / Cloud Run / Azure Container Apps** | Push the Docker image, set env vars, mount a persistent volume / secret for `.secret_key`, point `DATABASE_URL` at the managed Postgres. |

---

## 6. Frontend deployment

The frontend is a **Vite-built static site**. There is no SSR.

### 6.1 Build

```bash
cd frontend
npm ci
VITE_API_URL='https://api.jobcopilot.example.com' npm run build
```

> `VITE_API_URL` is read **at build time** (see [frontend/api.js](frontend/api.js#L3)). If you forget to set it, the bundle hard-codes `http://localhost:8000` and will fail in production.

The output lands in `frontend/dist/`.

### 6.2 Host the static files

The app uses **hash-based routing** (`#/setup`, `#/quick-start`, …) so you do **not** need SPA rewrites — any static host works.

**Netlify / Vercel / Cloudflare Pages**

| Setting | Value |
|---|---|
| Base directory | `frontend` |
| Build command | `npm run build` |
| Publish directory | `frontend/dist` |
| Env var | `VITE_API_URL=https://api.jobcopilot.example.com` |

**Nginx (self-hosted)**

```nginx
server {
  listen 443 ssl http2;
  server_name app.jobcopilot.example.com;
  root /var/www/jobcopilot/dist;
  index index.html;

  ssl_certificate     /etc/letsencrypt/live/app.jobcopilot.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/app.jobcopilot.example.com/privkey.pem;

  location / {
    try_files $uri /index.html;
  }

  # Long cache for hashed assets
  location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
  }
}
```

Deploy by `rsync`-ing `frontend/dist/` to `/var/www/jobcopilot/dist/`.

---

## 7. Chrome extension distribution

The extension lives in [extension/](extension/) and is **Manifest V3** (`activeTab` + `scripting` permissions, no static `host_permissions`).

### 7.1 Point it at your production frontend

The dashboard URL is read from `chrome.storage.sync` under the key `frontendBaseUrl` and falls back to `http://localhost:5173` (see [extension/popup.js](extension/popup.js#L75)). Two paths to make production users hit your hosted frontend:

**A. Bake it into a private build (recommended).** Edit `DEFAULT_FRONTEND_URL`:

```js
const DEFAULT_FRONTEND_URL = 'https://app.jobcopilot.example.com';
```

Bump `manifest.json` `version`, then repackage.

**B. Let users override it themselves.** They open `chrome://extensions` → Inspect popup → Console:

```js
await chrome.storage.sync.set({ frontendBaseUrl: 'https://app.jobcopilot.example.com' });
```

> There is currently no options-page UI for this — option A is far less error-prone for end users.

### 7.2 Package and publish

```bash
cd extension
zip -r ../jobcopilot-extension-v$(jq -r .version manifest.json).zip . \
  -x '*.DS_Store' -x 'PRIVACY.md'
```

Upload the ZIP to the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole) ($5 one-time registration). For internal testing, use **Unlisted** visibility or distribute the ZIP and have users **Load unpacked**.

### 7.3 Manifest hardening before publishing

The current manifest works but you should review before going public:

- The `name`/`short_name`/`description` still say "Job Extractor". Rename to match your published brand.
- Provide a privacy policy URL — [extension/PRIVACY.md](extension/PRIVACY.md) is a starting point; host it publicly and link it in the Web Store listing.

---

## 8. Production hardening checklist

The dev defaults need to be tightened before exposing the service.

| Area | Current state | Fix before prod |
|---|---|---|
| **CORS** | [backend/app/main.py](backend/app/main.py#L88) sets `allow_origins=["*"]` | Restrict to your frontend origin(s) — e.g. `["https://app.jobcopilot.example.com"]` and the extension origin `chrome-extension://<id>`. |
| **TLS** | Backend serves plain HTTP on `:8000` | Terminate TLS at Nginx / the PaaS load balancer; never expose `:8000` directly. |
| **Database TLS** | URL has no `sslmode` | Append `?sslmode=require` to `DATABASE_URL`. |
| **Secrets** | `.env` file in the repo path | Use the host's secret manager (AWS SM, GCP Secret Manager, Render/Fly secrets) and inject as env vars. **Never commit `backend/app/.env` or `backend/app/.secret_key`.** |
| **`.secret_key` durability** | Generated lazily on first save | Persist across deploys (volume or secret manager); back it up. |
| **Auth** | No authentication on any endpoint | This is a single-user demo today. If you put it on the public internet, add API-key middleware or sit it behind an SSO proxy (Cloudflare Access, Tailscale Funnel, oauth2-proxy). |
| **Rate limiting** | None | Add a limiter (Nginx `limit_req_zone`, Cloudflare, or `slowapi` middleware) — the LLM endpoints are expensive. |
| **Observability** | Logfire + Sentry SDK already wired | Set `LOGFIRE_TOKEN`, `SENTRY_DSN`, `APP_ENV=prod`, `APP_VERSION=<git-sha>`. |
| **Background jobs** | Orchestrator runs in-process via `background=true` | Fine for low traffic. For higher load move to a real queue (RQ/Celery/Arq) and a separate worker process. |
| **Backups** | None configured | Enable daily snapshots on the managed Postgres; test restore. |

---

## 9. Smoke test after deploy

```bash
# 1. Backend is up
curl -fsS https://api.jobcopilot.example.com/docs | head -1

# 2. DB is reachable + tables exist
curl -fsS -X POST https://api.jobcopilot.example.com/api/jobs/ingest \
  -H 'Content-Type: application/json' \
  -d '{"raw_text":"Senior Python engineer with FastAPI experience"}'

# 3. LLM credentials work (mock or real)
JOB_ID=...   # from previous response
RESUME_ID=...
curl -fsS -X POST https://api.jobcopilot.example.com/api/orchestrate \
  -H 'Content-Type: application/json' \
  -d "{\"job_id\":\"$JOB_ID\",\"resume_id\":\"$RESUME_ID\",\"background\":true}"

# 4. Frontend loads
curl -fsS https://app.jobcopilot.example.com/ | grep -q '<div id="app"'

# 5. Extension flow
#    Click extension → Extract on a LinkedIn job → "Open in Dashboard"
#    expect a tab at https://app.jobcopilot.example.com/#/quick-start?payload=...
```

---

## 10. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Backend logs `psycopg.OperationalError: could not connect to server` | `DATABASE_URL` wrong driver (`postgresql://` instead of `postgresql+psycopg://`), or host firewall, or missing `sslmode=require`. |
| Backend startup loops with `relation "..." does not exist` | SQL migrations in [backend/app/db/migrations/](backend/app/db/migrations/) were not applied to the target DB. |
| Frontend calls hit `http://localhost:8000` from a deployed site | `VITE_API_URL` was not set at **build** time. Rebuild with the env var, then redeploy. |
| Browser blocks frontend → backend calls with a CORS error | Tighten / fix `allow_origins` in [backend/app/main.py](backend/app/main.py#L88) to include the exact frontend origin (scheme + host + port). |
| Interview-research agent fails with provider errors | Requires `LLM_PROVIDER=google` with a valid `GOOGLE_API_KEY` — other providers don't expose the web-search tool the agent depends on. |
| `Setup` screen says provider is configured but agents fail with "API key missing" | The container was redeployed and `backend/app/.secret_key` was not persisted, so the encrypted DB entry can no longer be decrypted. Re-enter the key in **Setup** or restore the secret file. |
| Extension opens `http://localhost:5173/...` on a user's machine | They are running an old build where `DEFAULT_FRONTEND_URL` still points at localhost. Ship a new packaged version (§7.1 option A). |
| 504 / timeout from the frontend during analysis | Reverse-proxy timeout shorter than the backend's. Set Nginx `proxy_read_timeout 360s;` (and the PaaS equivalent). |

---

## 11. Quick reference

| Component | Working dir | Build | Run |
|---|---|---|---|
| Backend | `backend/` | `pip install -r app/requirements.txt gunicorn` | `gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --timeout 360` |
| Frontend | `frontend/` | `VITE_API_URL=https://api.example.com npm run build` | Serve `frontend/dist/` from any static host |
| Extension | `extension/` | Edit `DEFAULT_FRONTEND_URL`, bump `manifest.json` version | Zip the folder → upload to Chrome Web Store, or **Load unpacked** for internal use |
| Migrations | `backend/app/db/migrations/` | — | `psql "$DATABASE_URL_PSQL" -f 000N_*.sql` for each file in order |
