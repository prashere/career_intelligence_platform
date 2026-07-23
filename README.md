# Career Intelligence System

A personal career intelligence companion that helps ambitious students and early-career professionals discover, understand, prioritize, and act on opportunities aligned with long-term goals.

## What it does

- **Discovers** opportunities via automated RSS/HTML/JSON ingestion
- **Ranks** them against your profile with explainable fit scores
- **Organizes** cards through Updated → In Progress lifecycle
- **Assists** with RAG-grounded Q&A and agentic research tools
- **Tracks** applications, learning progress, deadlines, and weekly focus
- **Notifies** via email digest and deadline reminders

## Architecture

```
Frontend (React/Vite) → FastAPI → PostgreSQL + pgvector
                              ↘ Celery workers (ingest, notify, rank)
                              ↘ LangGraph agent + RAG
```

## Quick start

### Prerequisites

- Docker & Docker Compose
- (Optional) OpenAI API key for embeddings, chat, and agent features
- (Optional) Tavily API key for web search in agent mode
- (Optional) Resend/SMTP for email notifications

### Run locally

```bash
cp .env.example .env
# Edit .env with your API keys

docker compose up --build
```

Services:
- **API:** http://localhost:8000 (docs at /docs)
- **Frontend:** http://localhost:5173

### Seed sample data

```bash
docker compose exec api python scripts/seed.py
```

### Trigger ingestion

```bash
curl -X POST http://localhost:8000/api/v1/ingest/fetch-all
curl -X POST http://localhost:8000/api/v1/ingest/normalize
curl -X POST http://localhost:8000/api/v1/profile/rank
```

## Project structure

```
backend/          FastAPI, SQLAlchemy, Celery, LangGraph agent, RAG
frontend/         React + Vite + TypeScript
infra/            DB init scripts
docs/             Architecture decision records
.github/          CI workflows
```

## Key API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/feed` | Opportunities feed with filters |
| `GET /api/v1/opportunities/{id}` | Card detail |
| `POST /api/v1/opportunities/{id}/agent` | Agentic chat |
| `GET /api/v1/dashboard` | Updated / In Progress / Upskilling |
| `GET /api/v1/planning/weekly` | Weekly focus view |
| `PATCH /api/v1/profile` | Update goals and re-rank |

## Deployment

See [docs/deployment.md](docs/deployment.md) for Railway/Fly.io instructions.

## Portfolio highlights

- Automated multi-source ingestion with deduplication
- pgvector embedding-based personalization with explainable ranking
- Hybrid RAG retrieval (BM25-style + vector)
- LangGraph-style agent with tools: web search, checklist, calendar, reminders
- Celery beat schedules for ingest, rank, digest, and deadline reminders
- Structured logging + Sentry integration ready

## Boundaries

This system supports career decisions—it does not replace mentors, write applications, or guarantee outcomes.

## License

MIT
