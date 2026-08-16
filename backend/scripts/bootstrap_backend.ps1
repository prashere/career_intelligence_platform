#!/usr/bin/env pwsh
# Install backend Python dependencies (including asyncpg, playwright).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing Python requirements..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Warn "Full requirements install failed (common on Python 3.14 without pg_config)."
  Write-Host "Installing core runtime packages..."
  python -m pip install asyncpg pgvector sqlalchemy httpx feedparser beautifulsoup4 lxml `
    python-dateutil rapidfuzz pyyaml pydantic pydantic-settings alembic playwright greenlet `
    bcrypt python-jose email-validator python-multipart structlog pytest pytest-asyncio
}

Write-Host "Installing Playwright Chromium (ScholarshipTab / DAAD browser fallback)..."
python -m playwright install chromium

Write-Host ""
Write-Host "Done. Verify with:"
Write-Host "  python scripts/validate_discover_strategies.py --timeout 60"
Write-Host "  python scripts/validate_discover_strategies.py --timeout 60 --include-browser"
Write-Host "  python scripts/run_ingestion_e2e.py"
