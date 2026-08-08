"""Admin routes — scheduler management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.models import ScheduleKind, SchedulerJob, User
from app.schemas.admin import SchedulerJobResponse, SchedulerJobUpdate
from app.services.schedulers import seed_scheduler_jobs

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/schedulers", response_model=list[SchedulerJobResponse])
async def list_schedulers(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SchedulerJob).order_by(SchedulerJob.category, SchedulerJob.name))
    return result.scalars().all()


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
    return job


@router.post("/schedulers/seed", response_model=dict)
async def seed_schedulers(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    added = await seed_scheduler_jobs(db)
    return {"seeded": added}
