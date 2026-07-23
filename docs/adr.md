# ADR 001: Personal-First, Single-User Architecture

## Status
Accepted

## Context
The system is built first as a personal tool for daily use and portfolio demonstration.

## Decision
- Defer multi-user auth until core value is proven
- Use a single default user profile seeded on first run
- All API endpoints operate on the default user

## Consequences
- Faster iteration and simpler deployment
- Auth layer can be added later without changing core models

---

# ADR 002: Python-First Stack with Agentic AI Layer

## Status
Accepted

## Context
Portfolio goal requires demonstrating senior agentic AI/ML engineering.

## Decision
- Backend: FastAPI + SQLAlchemy + Celery
- Storage: PostgreSQL + pgvector
- AI: OpenAI embeddings + LangGraph-style agent orchestration
- Frontend: React + Vite + TypeScript

## Consequences
- Strong separation between ingestion, intelligence, and UI layers
- Agent tools are modular and testable independently

---

# ADR 003: System Boundaries

## Status
Accepted

## Context
Blueprint defines what the system is and is not responsible for.

## Decision
The system will NOT become:
- A general productivity platform
- A social network
- An application essay writing service

It WILL support discovery, understanding, organization, planning, and informed action.

## Consequences
Features are evaluated against career growth responsibilities before implementation.
