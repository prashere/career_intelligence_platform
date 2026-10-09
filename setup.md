# Setup Guide

This guide walks you through running the Career Intelligence Platform on your own computer. You do not need to install Python or Node by hand. Docker runs the database, the API, background workers, and the website together.

When you are done, you will have:

- The website at [http://localhost:5173](http://localhost:5173)
- The API at [http://localhost:8000](http://localhost:8000) (interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs))

---

## What you need

| Requirement | Why |
| --- | --- |
| **Docker** | Runs every service for you. [Docker Desktop](https://www.docker.com/products/docker-desktop/) is the simplest choice on Mac, Windows, and Linux. [Colima](https://github.com/abiosoft/colima) also works on Mac/Linux. |
| **Git** | To copy the project onto your machine. |
| **A Groq API key** | Needed for CV reading, chat, and the career assistant. Groq has a free tier. See [API keys](#3-get-your-api-keys) below. |

Give Docker at least **4 GB of RAM**. The first start downloads images and can take several minutes.

These local ports must be free: **5432** (Postgres), **6379** (Redis), **8000** (API), **5173** (website). If another app is using one of them, stop it first or you will see a “port is already allocated” error.

---

## 1. Install Docker

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and open it.
2. Wait until it says Docker is running.
3. Confirm in a terminal:

```bash
docker --version
docker compose version
```

Both commands should print a version number, not an error.

If you use Colima instead of Docker Desktop:

```bash
colima start
docker --version
```

---

## 2. Open the project

```bash
git clone <your-repository-url>
cd career_intelligence_platform
```

If you already have the folder, just `cd` into it.

---

## 3. Get your API keys

The app can start without any keys. You can register, open the dashboard, and click around. **Matching from a real CV, opportunity chat, and the assistant will not work until a chat key is set.**

### Required for AI features: Groq

Groq is the default chat provider. It is used to:

- Read a CV during profile setup
- Answer questions about an opportunity
- Power the career assistant

1. Create a free account at [https://console.groq.com](https://console.groq.com).
2. Open [API Keys](https://console.groq.com/keys) and create a key.
3. Copy it. You will paste it into `.env` in the next step as `GROQ_API_KEY`.

Keep this key private. Never commit it to Git.

You can use OpenAI instead of Groq. Set `LLM_PROVIDER=openai` and fill in `OPENAI_API_KEY`. Groq is the path this project is set up for, and it has a free tier.

### Optional keys

Leave these blank unless you need the extra feature.

| Variable | Used for | Get it from |
| --- | --- | --- |
| `OPENAI_API_KEY` | Cloud embeddings for ranking and search. If empty, the app falls back to a local model, then to plain text matching. | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `TAVILY_API_KEY` | Web search. Needed to confirm listings on official pages and to discover new sources. Without it, those checks are skipped. | [Tavily](https://tavily.com) |
| `LANGSMITH_API_KEY` | Traces LLM calls in LangSmith (useful while developing). | [LangSmith settings](https://smith.langchain.com/settings) |
| `RESEND_API_KEY` or SMTP settings | Email digest and deadline reminders. In-app notifications still work without email. | [Resend](https://resend.com) or your SMTP host |

`LANGSMITH_TRACING` can stay `true` even if you have no LangSmith key. Tracing simply stays off until a key is present.

---

## 4. Create your environment file

From the project root:

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in at least:

```env
GROQ_API_KEY=gsk_your_key_here
```

Also change these before you treat this as anything other than a private demo:

```env
SECRET_KEY=pick-a-long-random-string
BOOTSTRAP_ADMIN_EMAIL=admin@localhost.dev
BOOTSTRAP_ADMIN_PASSWORD=choose-a-strong-password
```

The first time the API starts and the users table is empty, it creates an administrator from `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`. Remember those values. You will use them to sign in.

Leave `DATABASE_URL`, Redis, and the Groq model names as they are. Docker overrides the database and Redis URLs so containers can talk to each other.

`.env` is listed in `.gitignore`. Do not add it to Git.

---

## 5. Start everything

From the project root:

```bash
docker compose up --build
```

The first run builds images and installs Python packages. That often takes 5–15 minutes. Later starts are much faster.

You should see these services become healthy or start logging:

| Service | Role |
| --- | --- |
| `db` | PostgreSQL with pgvector |
| `redis` | Job queue |
| `api` | FastAPI app (runs database migrations, then serves HTTP) |
| `worker` | Celery worker (ingestion, ranking, notifications, profile pipeline) |
| `beat` | Celery beat (hourly ingest, daily ranking, daily notifications) |
| `frontend` | Vite + React website |

Leave this terminal open. Logs will keep scrolling. That is expected.

To run in the background instead:

```bash
docker compose up --build -d
```

Then inspect logs with `docker compose logs -f`.

---

## 6. Check that it is running

In a **new** terminal:

```bash
curl http://localhost:8000/api/v1/health
```

You should see:

```json
{"status":"ok","version":"0.1.0"}
```

Open these in a browser:

- Website: [http://localhost:5173](http://localhost:5173)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

The website should show a sign-in page.

If `curl` fails, wait a bit longer. The API only starts after `alembic upgrade head` finishes. Check `docker compose logs api`.

---

## 7. Sign in

1. Go to [http://localhost:5173/login](http://localhost:5173/login).
2. Use the bootstrap admin from `.env`:
   - Email: `admin@localhost.dev` (or whatever you set)
   - Password: the `BOOTSTRAP_ADMIN_PASSWORD` value
3. You should land on the dashboard. It will be empty. That is expected: this project does not pre-load sample opportunities.

The admin account can open **Sources**, **Ingestion**, **Ingestion lab**, and **Background tasks** in the sidebar.

To use the product as a normal person, open [http://localhost:5173/register](http://localhost:5173/register) and create a second account. That user will not see the admin pages.

The bootstrap admin is created only when the database has **no users yet**. If you already started the app once, changing those two variables will not create a new admin.

---

## 8. Complete a profile (the real product path)

AI features in this step need `GROQ_API_KEY`.

1. Sign in.
2. Open **Profile setup** (or [http://localhost:5173/profile/setup](http://localhost:5173/profile/setup)).
3. Work through the steps: about you, CV, education, goals, preferences, review.
4. Upload a PDF or paste CV text. Submit.

Background workers then:

1. Turn form answers into a structured profile
2. Extract details from the CV with Groq
3. Merge, validate, and compile matching rules
4. Select public aggregators for this profile
5. Fetch live listings, score them, and fill the dashboard

Watch progress on **Profile**. The dashboard fills in as ranking finishes. The first ingest can take several minutes.

A new account starts with an **empty** dashboard on purpose. Nothing is pre-loaded. Matches appear only after this profile is submitted and ingestion runs.

---

## 9. Stop, start again, or reset

Stop (keeps the database):

```bash
docker compose down
```

Start again later (no rebuild needed unless you changed Dockerfiles or dependencies):

```bash
docker compose up
```

Wipe the database and start clean (deletes all users, profiles, and opportunities):

```bash
docker compose down -v
docker compose up --build
```

After a volume wipe, the bootstrap admin is created again on the next API start.

---

## Everyday commands

```bash
# Start
docker compose up

# Stop
docker compose up -d          # background
docker compose down

# Logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend

# Rebuild after dependency changes
docker compose up --build
```

---

## Troubleshooting

**`docker: permission denied` or `cannot connect to the Docker daemon`**  
Docker is not running. Open Docker Desktop, or run `colima start`, then retry.

**`env file .env not found`**  
You skipped step 4. Run `cp .env.example .env` in the project root.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`** (or 6379 / 8000 / 5173)  
Something else is using that port. On macOS you can check with:

```bash
lsof -nP -iTCP:5432,6379,8000,5173 -sTCP:LISTEN
```

Stop the other process, then run `docker compose up` again.

**Website loads but sign-in fails / API calls fail**  
Wait until `curl http://localhost:8000/api/v1/health` returns `{"status":"ok"}`. Then confirm `.env` has `CORS_ORIGINS=http://localhost:5173,http://localhost:3000`.

**Profile setup fails on “extract_cv” or Groq errors**  
`GROQ_API_KEY` is missing, invalid, or the free-tier rate limit was hit. Confirm the key in `.env`, then restart:

```bash
docker compose up -d --force-recreate api worker
```

**Dashboard stays empty after submit**  
That is expected until profile setup finishes and the worker fetches listings. Check `docker compose logs -f worker`. Some sources are slow or blocked. Do not load sample listings — this project does not ship personal or authentic seed data.

**Admin pages are missing**  
You signed in as a normal user. Use the bootstrap admin, or promote an existing user:

```bash
docker compose exec api python scripts/promote_admin.py you@example.com
```

**Want a full reset after a broken first run**

```bash
docker compose down -v
# Fix .env if needed
docker compose up --build
```

---

## What “working” looks like

You are set up correctly when all of this is true:

1. `curl http://localhost:8000/api/v1/health` returns `{"status":"ok","version":"0.1.0"}`
2. [http://localhost:5173](http://localhost:5173) shows the sign-in page
3. You can sign in with the bootstrap admin
4. The dashboard loads empty until you finish profile setup and ingestion runs
5. With a Groq key, profile setup can extract a CV and start matching

For what the product does and how the pieces fit together, see [README.md](README.md).
