# Backend scripts

Run from the `backend/` directory unless noted. Registry-backed scripts read
`career_intelligence_platform/.env` when you run from the platform root (see
`test_groq.py`). Set `PROJECT_ROOT` to the platform root when not using Docker.

```bash
cd backend
python scripts/<script>.py
```

---

## Pipeline documentation

Locked reference docs (submit → 100%):

- [Profile setup pipeline](../../docs/profile-setup-pipeline.md) — intake form, CV extraction LLM, merge, compile, activate
- [Ingestion pipeline](../../docs/ingestion-pipeline.md) — source fetch, relevance gate, ranking after activate

---

## Profile pipeline

| Script | What it does | How to run |
|--------|----------------|------------|
| `prefill_structured.py` | Builds `structured-profile.prefill.json` from a raw intake submission using rules (no LLM). Selects aggregators from `config/sources/source-registry.yaml`. | `python scripts/prefill_structured.py` or `python scripts/prefill_structured.py path/to/raw-submission.json` |
| `merge_profile.py` | Merges prefill JSON and CV extraction output into a candidate `structured-profile.json`. | `python scripts/merge_profile.py` or `python scripts/merge_profile.py path/to/extraction-output.json` |
| `compile_profile.py` | Compiles L3 artifacts (including `ingestion_sources.json`) from structured profile data. Resolves RSS URLs from the source registry. | `python scripts/compile_profile.py` or `python scripts/compile_profile.py path/to/structured-profile.json` |
| `validate_extraction.py` | Validates an extraction JSON file against the `StructuredProfile` Pydantic schema. | `python scripts/validate_extraction.py path/to/extraction-output.json` |
| `check_profile_ready.py` | Checks that compiled profile artifacts exist and the package is ready for ingestion. | `python scripts/check_profile_ready.py` or `python scripts/check_profile_ready.py --expected-sources 4` |
| `sync_profile_to_db.py` | Loads structured profile JSON into the `user_profiles` table for ranking. | `python scripts/sync_profile_to_db.py` or `python scripts/sync_profile_to_db.py --email you@example.com` |

---

## Source registry and ingestion

| Script | What it does | How to run |
|--------|----------------|------------|
| `list_source_registry.py` | Prints aggregators from `config/sources/source-registry.yaml`. With `--validate`, checks required fields and `parser_config` blocks. | `python scripts/list_source_registry.py` or `python scripts/list_source_registry.py --validate` |
| `validate_discover_strategies.py` | Live-probes discover strategies for every registry aggregator (or one). Reports pass/fail, winning strategy, and sample URLs. | `python scripts/validate_discover_strategies.py --timeout 90` or `python scripts/validate_discover_strategies.py --aggregator bigfuture --include-browser` |
| `seed_sources_from_profile.py` | Seeds `opportunity_sources` in the DB from compiled `ingestion_sources.json`, enriched from the registry. | `python scripts/seed_sources_from_profile.py` or `python scripts/seed_sources_from_profile.py path/to/ingestion_sources.json` |
| `cleanup_pipeline_data.py` | Wipes profile, ingestion, and opportunity DB rows; keeps `users` and `scheduler_jobs`. Registry YAML on disk is untouched. | `python scripts/cleanup_pipeline_data.py` (dry-run) · `python scripts/cleanup_pipeline_data.py --execute --flush-redis` |
| `run_ingestion_e2e.py` | End-to-end test: seeds from registry if empty, syncs envelope, runs all active sources, prints JSON summary. | `python scripts/run_ingestion_e2e.py` or `python scripts/run_ingestion_e2e.py --include-browser --max-items 15` |

---

## Relevance gate

The gate scores discovered items into `admit` / `investigate` / `reject`. Tune it in
`config/sources/relevance-config.yaml`, then re-run these to see the effect.

| Script | What it does | How to run |
|--------|----------------|------------|
| `probe_relevance.py` | Scores titles through the gate offline, with no network calls. Runs a built-in regression set by default. | `python scripts/probe_relevance.py` or `python scripts/probe_relevance.py "Chevening Scholarship 2026" --url https://x.org/scholarships/a` |
| `validate_relevance_gate.py` | Live-discovers every registry aggregator and reports the verdict split per source. Use `--show-items` to see each decision and its evidence. | `python scripts/validate_relevance_gate.py --timeout 45` or `python scripts/validate_relevance_gate.py --aggregator profellow --show-items` |
| `smoke_playground.py` | Runs the Ingestion lab code path against one aggregator, including DB writes. Needs a database, so run it inside Docker. | `docker compose exec api python scripts/smoke_playground.py opportunitydesk --resolve` |

| `score_distribution.py` | Histogram of composite scores, fit levels, degraded components, missing deadlines. | `python scripts/score_distribution.py` or `python scripts/score_distribution.py --user-email you@example.com` |
| `show_card_reasons.py` | Prints the explanation payload the dashboard receives per card: fit level, percent, one-line summary, and every structured reason. Needs a database, so run it inside Docker. | `docker compose exec -e PYTHONPATH=/app api python scripts/show_card_reasons.py 5` |

---

| Script | What it does | How to run |
|--------|----------------|------------|
| `seed.py` | Removes leftover authentic sample rows from older versions. Does not copy any real profile. Optional `--fictional-demo` inserts clearly fake placeholder cards that stay hidden after profile setup. | `python scripts/seed.py` or `python scripts/seed.py --fictional-demo` |
| `promote_admin.py` | Sets an existing user's role to administrator. | `python scripts/promote_admin.py admin@localhost` |
| `test_groq.py` | Verifies `GROQ_API_KEY` and runs a sample chat (optional `--stream`). Run from platform root so `.env` is found. | `cd .. && python backend/scripts/test_groq.py` |
| `test_langsmith.py` | Verifies LangSmith tracing config and sends a traced test chat. | `cd .. && python backend/scripts/test_langsmith.py` |
| `bootstrap_backend.ps1` | Installs Python dependencies and Playwright Chromium on Windows (PowerShell). | `.\scripts\bootstrap_backend.ps1` from `backend/` |
