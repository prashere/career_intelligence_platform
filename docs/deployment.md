# Deployment Guide

## Railway (recommended for solo deploy)

1. Create a new Railway project
2. Add services:
   - **PostgreSQL** (enable pgvector extension via SQL: `CREATE EXTENSION vector;`)
   - **Redis**
   - **API** from `backend/Dockerfile`
   - **Worker** same image, command: `celery -A app.workers.celery_app worker --loglevel=info`
   - **Beat** same image, command: `celery -A app.workers.celery_app beat --loglevel=info`
   - **Frontend** from `frontend/Dockerfile` (or deploy to Vercel/Netlify)

3. Set environment variables from `.env.example`

4. Run migrations/seed once:
   ```bash
   railway run python scripts/seed.py
   ```

## Fly.io

Use `fly.toml` files in `infra/` as starting points. Deploy API and worker as separate apps sharing Postgres and Redis.

## Observability

- Set `SENTRY_DSN` for error tracking
- API exposes structured logs via structlog
- Health check: `GET /api/v1/health`

## Backup

- Enable automated Postgres backups on your provider
- Export opportunities weekly via API for redundancy

## Security notes

- Single-user mode: no auth by default (personal tool)
- For public demo: add magic-link auth before exposing
- Never commit `.env` with real API keys
