from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Application,
    LearningItem,
    Opportunity,
    OpportunityType,
    Requirement,
    UserOpportunity,
    UserOpportunityStatus,
    UserProfile,
)
from app.schemas import (
    FeedResponse,
    FeedSummary,
    OpportunityResponse,
    WeeklyFocusResponse,
)
from app.services.ranking import days_until, urgency_label


def empty_feed() -> FeedResponse:
    summary = FeedSummary(new_since=0, deadlines_this_week=0, prep_milestones_due=0)
    return FeedResponse(summary=summary, scholarships=[], fellowships=[], other=[])


def _to_response(opp: Opportunity, uo: Optional[UserOpportunity] = None) -> OpportunityResponse:
    d = days_until(opp.deadline)
    return OpportunityResponse(
        id=opp.id,
        title=opp.title,
        summary=opp.summary,
        institution=opp.institution,
        program=opp.program,
        opportunity_type=opp.opportunity_type.value if opp.opportunity_type else "other",
        url=opp.url,
        deadline=opp.deadline,
        opens_at=opp.opens_at,
        tags=opp.tags or [],
        requirements=opp.requirements or [],
        status=uo.status.value if uo else None,
        fit_score=uo.fit_score if uo else None,
        fit_level=uo.fit_level.value if uo and uo.fit_level else None,
        fit_explanation=uo.fit_explanation if uo else None,
        days_until_deadline=d,
        urgency_label=urgency_label(d),
    )


async def get_feed(
    session: AsyncSession,
    user_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    opportunity_type: Optional[str] = None,
    funding_type: Optional[str] = None,
    *,
    apply_eligibility: bool = True,
) -> FeedResponse:
    from app.ingestion.eligibility import load_eligibility_rules, passes_eligibility

    query = (
        select(Opportunity, UserOpportunity)
        .outerjoin(
            UserOpportunity,
            (UserOpportunity.opportunity_id == Opportunity.id) & (UserOpportunity.user_id == user_id),
        )
        .order_by(UserOpportunity.fit_score.desc().nullslast(), Opportunity.created_at.desc())
    )

    if search:
        query = query.where(
            or_(
                Opportunity.title.ilike(f"%{search}%"),
                Opportunity.summary.ilike(f"%{search}%"),
                Opportunity.search_vector.ilike(f"%{search.lower()}%"),
            )
        )

    if status:
        query = query.where(UserOpportunity.status == status)

    if opportunity_type:
        query = query.where(Opportunity.opportunity_type == opportunity_type)

    if funding_type:
        query = query.where(Opportunity.funding_type == funding_type)

    result = await session.execute(query)
    rows = result.all()
    eligibility_rules = load_eligibility_rules() if apply_eligibility else {}

    profile = await session.get(UserProfile, user_id) if apply_eligibility else None

    scholarships, fellowships, other = [], [], []
    now = datetime.now(timezone.utc)
    week_ahead = now + timedelta(days=7)
    tuesday = now - timedelta(days=(now.weekday() - 1) % 7)

    new_since = 0
    deadlines_week = 0

    for opp, uo in rows:
        if apply_eligibility and eligibility_rules and not passes_eligibility(opp, eligibility_rules, profile):
            continue
        resp = _to_response(opp, uo)
        if opp.created_at and opp.created_at >= tuesday:
            new_since += 1
        if opp.deadline and opp.deadline <= week_ahead:
            deadlines_week += 1

        if opp.opportunity_type == OpportunityType.scholarship:
            scholarships.append(resp)
        elif opp.opportunity_type == OpportunityType.fellowship:
            fellowships.append(resp)
        else:
            other.append(resp)

    prep_due = await session.execute(
        select(Requirement).where(Requirement.is_completed.is_(False), Requirement.due_date <= week_ahead)
    )

    return FeedResponse(
        summary=FeedSummary(
            new_since=new_since,
            deadlines_this_week=deadlines_week,
            prep_milestones_due=len(prep_due.scalars().all()),
            last_checked=now,
        ),
        scholarships=scholarships,
        fellowships=fellowships,
        other=other,
    )


async def get_opportunity_detail(
    session: AsyncSession, user_id: str, opportunity_id: str
) -> Optional[OpportunityResponse]:
    opp = await session.get(Opportunity, opportunity_id)
    if not opp:
        return None
    result = await session.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    uo = result.scalar_one_or_none()
    return _to_response(opp, uo)


async def update_user_opportunity(
    session: AsyncSession,
    user_id: str,
    opportunity_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> UserOpportunity:
    result = await session.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    uo = result.scalar_one_or_none()
    if not uo:
        uo = UserOpportunity(user_id=user_id, opportunity_id=opportunity_id)
        session.add(uo)
    if status:
        uo.status = UserOpportunityStatus(status)
    if notes is not None:
        uo.notes = notes
    await session.commit()
    await session.refresh(uo)
    return uo


async def get_or_create_application(session: AsyncSession, user_opportunity_id: str) -> Application:
    result = await session.execute(
        select(Application).where(Application.user_opportunity_id == user_opportunity_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        app = Application(user_opportunity_id=user_opportunity_id)
        session.add(app)
        await session.commit()
        await session.refresh(app)
    return app


async def get_weekly_focus(session: AsyncSession, user_id: str) -> WeeklyFocusResponse:
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)

    deadlines = []
    result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity)
        .where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.status == UserOpportunityStatus.in_progress,
            Opportunity.deadline.isnot(None),
            Opportunity.deadline <= week_end,
        )
    )
    for uo, opp in result.all():
        deadlines.append({"title": opp.title, "deadline": opp.deadline.isoformat(), "id": opp.id})

    prep_tasks = []
    req_result = await session.execute(
        select(Requirement, UserOpportunity)
        .join(UserOpportunity)
        .where(
            UserOpportunity.user_id == user_id,
            Requirement.is_completed.is_(False),
            Requirement.due_date <= week_end,
        )
    )
    for req, uo in req_result.all():
        prep_tasks.append({"title": req.title, "due": req.due_date.isoformat() if req.due_date else None})

    learning_result = await session.execute(
        select(LearningItem).where(
            LearningItem.user_id == user_id,
            LearningItem.status != "completed",
        )
    )
    learning_tasks = [
        {"title": li.title, "progress": li.progress_percent, "status": li.status}
        for li in learning_result.scalars().all()
    ]

    summary_parts = []
    if deadlines:
        summary_parts.append(f"{len(deadlines)} deadline(s) this week")
    if prep_tasks:
        summary_parts.append(f"{len(prep_tasks)} prep task(s) due")
    if learning_tasks:
        summary_parts.append(f"{len(learning_tasks)} learning item(s) in progress")

    return WeeklyFocusResponse(
        deadlines=deadlines,
        prep_tasks=prep_tasks,
        learning_tasks=learning_tasks,
        focus_summary=" · ".join(summary_parts) if summary_parts else "No urgent items this week",
    )
