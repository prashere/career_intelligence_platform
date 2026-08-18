"""DB-backed caches for org domains and domain legitimacy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.verification import DomainLegitimacyCache, OrgDomainCache
from app.verification.domain_utils import extract_domain, is_institutional_domain, normalize_org_key
from app.verification.prescreen import scan_scam_phrases

logger = get_logger(__name__)


async def get_org_domain(session: AsyncSession, org_name: str) -> OrgDomainCache | None:
    key = normalize_org_key(org_name)
    if not key:
        return None
    result = await session.execute(select(OrgDomainCache).where(OrgDomainCache.org_key == key))
    return result.scalar_one_or_none()


async def save_org_domain(
    session: AsyncSession,
    org_name: str,
    canonical_domain: str,
    *,
    canonical_url: str | None = None,
    confidence: float = 0.7,
    meta: dict | None = None,
    commit: bool = True,
) -> OrgDomainCache:
    key = normalize_org_key(org_name)
    result = await session.execute(select(OrgDomainCache).where(OrgDomainCache.org_key == key))
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row:
        row.canonical_domain = canonical_domain
        row.canonical_url = canonical_url or row.canonical_url
        row.confidence = confidence
        row.verified_at = now
        if meta:
            row.meta = {**(row.meta or {}), **meta}
    else:
        row = OrgDomainCache(
            org_key=key,
            org_display_name=org_name[:255],
            canonical_domain=canonical_domain,
            canonical_url=canonical_url,
            confidence=confidence,
            verified_at=now,
            meta=meta or {},
        )
        session.add(row)
    if commit:
        await session.commit()
        await session.refresh(row)
    else:
        await session.flush()
    return row


async def get_domain_legitimacy(session: AsyncSession, domain: str) -> DomainLegitimacyCache | None:
    if not domain:
        return None
    result = await session.execute(
        select(DomainLegitimacyCache).where(DomainLegitimacyCache.domain == domain.lower())
    )
    return result.scalar_one_or_none()


async def _fetch_rdap_registration(domain: str) -> datetime | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"https://rdap.org/domain/{domain}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            for event in data.get("events") or []:
                if event.get("eventAction") == "registration":
                    raw = event.get("eventDate")
                    if raw:
                        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception as exc:
        logger.debug("rdap_lookup_failed", domain=domain, error=str(exc))
    return None


async def refresh_domain_legitimacy(
    session: AsyncSession,
    domain: str,
    *,
    page_text: str | None = None,
    force: bool = False,
    commit: bool = True,
) -> DomainLegitimacyCache:
    domain = domain.lower().strip()
    recheck_days = settings.verification_domain_recheck_days
    existing = await get_domain_legitimacy(session, domain)
    now = datetime.now(timezone.utc)

    if existing and not force:
        age = (now - existing.last_checked_at).days if existing.last_checked_at else recheck_days + 1
        if age < recheck_days:
            return existing

    flags: list[str] = []
    trust = 0.5

    if is_institutional_domain(domain):
        trust += 0.25
        flags.append("institutional_tld")

    registered_at = await _fetch_rdap_registration(domain)
    if registered_at:
        years = (now - registered_at).days / 365.25
        if years >= 5:
            trust += 0.15
            flags.append("domain_age_5y+")
        elif years < 1:
            trust -= 0.25
            flags.append("domain_age_under_1y")

    if page_text:
        scams = scan_scam_phrases(page_text)
        if scams:
            trust -= 0.4
            flags.extend([f"scam:{s}" for s in scams[:3]])

    trust = max(0.0, min(1.0, trust))

    if existing:
        existing.registered_at = registered_at or existing.registered_at
        existing.trust_score = round(trust, 3)
        existing.flags = flags
        existing.last_checked_at = now
        row = existing
    else:
        row = DomainLegitimacyCache(
            domain=domain,
            registered_at=registered_at,
            trust_score=round(trust, 3),
            flags=flags,
            last_checked_at=now,
        )
        session.add(row)

    if commit:
        await session.commit()
        await session.refresh(row)
    else:
        await session.flush()
    return row


def pick_canonical_domain_from_search(
    org_name: str,
    results: list[dict],
) -> tuple[str | None, str | None]:
    """Pick best domain from Tavily search results."""
    org_lower = org_name.lower()
    for hit in results:
        url = hit.get("url") or ""
        domain = extract_domain(url)
        if not domain:
            continue
        title = (hit.get("title") or "").lower()
        content = (hit.get("content") or "").lower()
        if org_lower.split()[0] in domain or org_lower.split()[0] in title:
            return domain, url
        if is_institutional_domain(domain):
            return domain, url
        if "official" in title or "official" in content[:200]:
            return domain, url
    if results:
        url = results[0].get("url") or ""
        return extract_domain(url), url
    return None, None
