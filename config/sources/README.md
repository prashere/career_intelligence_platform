# Source registry (git-tracked)

Canonical aggregator catalog and ingestion schema for the Career Intelligence Platform.

| File | Purpose |
|------|---------|
| `source-registry.yaml` | Aggregator entries: URLs, scoring metadata, `parser_config` (discover / extract / filters) |
| `ingestion-config.yaml` | Schema version, allowed discover kinds, validation defaults, field reference |

## Current catalog (10 aggregators)

| ID | Discover approach | Notes |
|----|-------------------|--------|
| `opportunitydesk` | RSS | WordPress feed |
| `youthop` | `youthop_api` hybrid | WordPress JSON API (feed 404) |
| `scholarships360` | RSS | `/research/` path filter |
| `bold` | sitemap | Scholarship detail URLs |
| `bigfuture` | `collegeboard_scholarships` | College Board JSON API |
| `careeronestop` | `jina_html` hybrid | Geo-blocked direct; Jina reader proxy |
| `scholarshipportal` | `jina_html` + browser fallback | mastersportal.com search listing |
| `scholarpositions` | `wp_json` + `proxy_prefix` | Cloudflare; WordPress API via Jina |
| `opportunitiescorners` | RSS | |
| `profellow` | RSS | |

`url` in the registry may be a **string** or a **one-item list** (RSS feeds). The backend normalizes lists to a single string for APIs and seeding.

## Discover kinds

Declared in `ingestion-config.yaml` and implemented in `backend/app/ingestion/discover/strategies.py`:

- **HTTP:** `rss`, `html`, `html_paginated`, `wp_json`, `sitemap`, `youthop_api`, `collegeboard_scholarships`, `jina_html`
- **Hybrid:** `kind: hybrid` with ordered `strategies[]`; optional `requires_browser` per strategy
- **Proxy:** `wp_json` accepts `proxy_prefix: https://r.jina.ai/` for bot-protected WordPress sites
- **Browser fallback:** set `fetch_mode: browser` and `requires_browser: true` on HTML strategies when needed

Profile prefill reads this catalog via `load_source_registry()`; production ingestion and the **Admin → Ingestion lab** use the same file (lab calls `GET /api/v1/admin/ingestion/registry`).

## Validate

From `backend/` (set `PROJECT_ROOT` to the platform root if not using Docker):

```bash
# Structural checks (required fields, parser_config blocks)
python scripts/list_source_registry.py --validate

# Live discover probes for every aggregator
python scripts/validate_discover_strategies.py --timeout 90

# Single aggregator
python scripts/validate_discover_strategies.py --aggregator bigfuture --timeout 90

# Include Playwright browser strategies (slower)
python scripts/validate_discover_strategies.py --include-browser --timeout 90
```

Expect **10/10 PASS** on HTTP-only validation after registry updates. Jina-backed sources may take up to 90s per probe.

## After editing the registry

1. Run validation commands above.
2. Re-seed DB sources if IDs or `parser_config` changed: `python scripts/seed_sources_from_profile.py` (or seed from registry in Admin ingestion).
3. Test in **Admin → Ingestion lab** (discover, then dry run against seeded sources).

## Related paths

- Discover runners: `backend/app/ingestion/discover/`
- Registry merge at seed/runtime: `backend/app/ingestion/registry_config.py`
- Playground / lab API: `backend/app/ingestion/playground.py`
