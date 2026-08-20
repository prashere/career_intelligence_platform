"""Admin routes — scheduler and ingestion management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.ingestion.envelope_store import load_envelope_from_compiled, sync_platform_envelope
from app.ingestion.playground import list_registry_aggregators, run_playground
from app.ingestion.runs import get_run_detail, recent_rejected, recent_runs, source_health
from app.models import IngestionRun, Opportunity, OpportunitySource, ScheduleKind, SchedulerJob, User
from app.schemas.admin import (
    CandidateApprovalRequest,
    CandidateApprovalResponse,
    CandidateSourceResponse,
    DiscoveryRunResponse,
    IngestionOverviewResponse,
    IngestionRunDetailResponse,
    IngestionRunResponse,
    PlaygroundRequest,
    PlaygroundResponse,
    RegistryAggregatorResponse,
    RejectedItemResponse,
    SchedulerJobResponse,
    SchedulerJobUpdate,
    SourceHealthResponse,
    TraceEventResponse,
)
from app.services.ingestion import fetch_source
from app.services.schedulers import scheduler_info_detail, seed_scheduler_jobs
from app.workers.ingest.tasks import fetch_all_sources_task, fetch_source_task
from app.workers.source_discovery.tasks import run_discovery_task
from app.source_discovery.contracts import SourceApprovalPayload
from app.source_discovery.service import (
    approve_candidate,
    build_approval_defaults,
    create_discovery_run,
    get_candidate,
    get_discovery_run,
    list_discovery_runs,
    list_run_candidates,
    reject_candidate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _scheduler_response(job: SchedulerJob) -> SchedulerJobResponse:
    data = SchedulerJobResponse.model_validate(job)
    detail = scheduler_info_detail(job.key)
    if detail:
        data.info_detail = detail
    return data


@router.get("/schedulers", response_model=list[SchedulerJobResponse])
async def list_schedulers(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SchedulerJob).order_by(SchedulerJob.category, SchedulerJob.name))
    return [_scheduler_response(job) for job in result.scalars().all()]


@router.patch("/schedulers/{job_key}", response_model=SchedulerJobResponse)
async def update_scheduler(
    job_key: str,
    body: SchedulerJobUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SchedulerJob).where(SchedulerJob.key == job_key))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Scheduler job not found")

    updates = body.model_dump(exclude_unset=True)
    if "schedule_kind" in updates and updates["schedule_kind"]:
        try:
            updates["schedule_kind"] = ScheduleKind(updates["schedule_kind"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid schedule_kind") from exc

    for field, value in updates.items():
        setattr(job, field, value)

    if job.schedule_kind == ScheduleKind.interval and not job.interval_seconds:
        job.interval_seconds = 3600

    await db.commit()
    await db.refresh(job)
    return _scheduler_response(job)


@router.post("/schedulers/seed", response_model=dict)
async def seed_schedulers(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    changed = await seed_scheduler_jobs(db, reset_defaults=True)
    return {"seeded": changed}


@router.post("/schedulers/{job_key}/run", response_model=dict)
async def run_scheduler_job(
    job_key: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SchedulerJob).where(SchedulerJob.key == job_key))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Scheduler job not found")

    from celery import current_app

    current_app.send_task(job.task_path)
    return {"queued": True, "task": job.task_path, "key": job.key}


@router.get("/ingestion/overview", response_model=IngestionOverviewResponse)
async def ingestion_overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_opps = await db.scalar(select(func.count()).select_from(Opportunity)) or 0
    sources = (await db.execute(select(OpportunitySource))).scalars().all()
    active = sum(1 for s in sources if s.is_active)
    with_errors = sum(1 for s in sources if s.last_error)
    last_run = await db.scalar(select(IngestionRun.started_at).order_by(desc(IngestionRun.started_at)).limit(1))
    verification_rows = await db.execute(
        select(Opportunity.verification_status, func.count())
        .where(Opportunity.duplicate_of.is_(None))
        .group_by(Opportunity.verification_status)
    )
    verification_counts = {
        (row[0] or "unverified"): row[1] for row in verification_rows.all()
    }
    return IngestionOverviewResponse(
        total_opportunities=total_opps,
        total_sources=len(sources),
        active_sources=active,
        sources_with_errors=with_errors,
        last_run_at=last_run,
        verification_counts=verification_counts,
    )


@router.get("/ingestion/sources", response_model=list[SourceHealthResponse])
async def ingestion_sources(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await source_health(db)


@router.get("/ingestion/runs", response_model=list[IngestionRunResponse])
async def ingestion_runs(
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await recent_runs(db, limit=limit)


@router.get("/ingestion/runs/{run_id}", response_model=IngestionRunDetailResponse)
async def ingestion_run_detail(
    run_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    detail = await get_run_detail(db, run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Run not found")
    run = detail["run"]
    return IngestionRunDetailResponse(
        run=IngestionRunResponse.model_validate(run),
        source_name=detail["source_name"],
        rejected_items=[RejectedItemResponse.model_validate(r) for r in detail["rejected_items"]],
        trace_events=[TraceEventResponse.model_validate(e) for e in detail["trace_events"]],
    )


@router.get("/ingestion/registry", response_model=list[RegistryAggregatorResponse])
async def ingestion_registry(_: User = Depends(require_admin)):
    return list_registry_aggregators()


@router.post("/ingestion/playground", response_model=PlaygroundResponse)
async def ingestion_playground(
    body: PlaygroundRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.source_id and not body.registry_id:
        raise HTTPException(status_code=400, detail="Provide source_id or registry_id")
    result = await run_playground(
        db,
        source_id=body.source_id,
        registry_id=body.registry_id,
        mode=body.mode,
        max_items=body.max_items,
        include_browser=body.include_browser,
        resolve_investigate=body.resolve_investigate,
    )
    return PlaygroundResponse(**result)


@router.get("/ingestion/rejected", response_model=list[RejectedItemResponse])
async def ingestion_rejected(
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await recent_rejected(db, limit=limit)


@router.post("/ingestion/sync-envelope")
async def sync_envelope(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    envelope = load_envelope_from_compiled()
    await sync_platform_envelope(db, envelope)
    return {"ok": True, "keys": list(envelope.keys())}


@router.post("/ingestion/verify-backfill")
async def trigger_verification_backfill(
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_admin),
):
    from app.workers.verification.tasks import verify_backfill_task

    verify_backfill_task.delay(limit=limit)
    return {"status": "queued", "limit": limit}


@router.post("/ingestion/fetch-all")
async def trigger_ingestion_fetch_all(_: User = Depends(require_admin)):
    fetch_all_sources_task.delay()
    return {"status": "queued"}


@router.post("/ingestion/sources/{source_id}/fetch")
async def trigger_source_fetch(
    source_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await fetch_source(db, source_id)
    return result


@router.post("/ingestion/sources/{source_id}/fetch-async")
async def trigger_source_fetch_async(source_id: str, _: User = Depends(require_admin)):
    fetch_source_task.delay(source_id)
    return {"status": "queued", "source_id": source_id}


@router.post("/source-discovery/runs", response_model=DiscoveryRunResponse)
async def trigger_source_discovery(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await create_discovery_run(db, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run_discovery_task.delay(run.id)
    return DiscoveryRunResponse.model_validate(run)


@router.get("/source-discovery/runs", response_model=list[DiscoveryRunResponse])
async def list_source_discovery_runs(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    runs = await list_discovery_runs(db, user.id, limit=limit)
    return [DiscoveryRunResponse.model_validate(r) for r in runs]


@router.get("/source-discovery/runs/{run_id}", response_model=DiscoveryRunResponse)
async def get_source_discovery_run(
    run_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    run = await get_discovery_run(db, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return DiscoveryRunResponse.model_validate(run)


@router.get(
    "/source-discovery/runs/{run_id}/candidates",
    response_model=list[CandidateSourceResponse],
)
async def list_source_discovery_candidates(
    run_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    run = await get_discovery_run(db, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    candidates = await list_run_candidates(db, run_id)
    return [CandidateSourceResponse.model_validate(c) for c in candidates]


@router.get("/source-discovery/candidates/{candidate_id}", response_model=CandidateSourceResponse)
async def get_source_discovery_candidate(
    candidate_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    candidate = await get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateSourceResponse.model_validate(candidate)


@router.get(
    "/source-discovery/candidates/{candidate_id}/approval-defaults",
    response_model=CandidateApprovalRequest,
)
async def get_candidate_approval_defaults(
    candidate_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    candidate = await get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    defaults = build_approval_defaults(candidate)
    return CandidateApprovalRequest.model_validate(defaults.model_dump())


@router.post("/source-discovery/candidates/{candidate_id}/reject", response_model=CandidateSourceResponse)
async def reject_source_discovery_candidate(
    candidate_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        candidate = await reject_candidate(db, candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CandidateSourceResponse.model_validate(candidate)


@router.post(
    "/source-discovery/candidates/{candidate_id}/approve",
    response_model=CandidateApprovalResponse,
)
async def approve_source_discovery_candidate(
    candidate_id: str,
    body: CandidateApprovalRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    payload = SourceApprovalPayload.model_validate(body.model_dump())
    try:
        result = await approve_candidate(db, candidate_id, payload, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CandidateApprovalResponse(**result)
