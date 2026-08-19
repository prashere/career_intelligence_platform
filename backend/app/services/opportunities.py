from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import func, not_, or_, select
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
    OpportunityListResponse,
    OpportunityResponse,
    WeeklyFocusResponse,
)
from app.services.affinity import append_status_history
from app.services.ranking import days_until, NEUTRAL_FIT_REASON, urgency_label

Bucket = Literal["matches", "closing_soon", "saved", "applied", "dismissed"]
SortMode = Literal["fit", "deadline"]


def empty_feed() -> FeedResponse:
    summary = FeedSummary(new_since=0, deadlines_this_week=0, prep_milestones_due=0)
    return FeedResponse(summary=summary, scholarships=[], fellowships=[], other=[])


def _to_response(opp: Opportunity, uo: Optional[UserOpportunity] = None) -> OpportunityResponse:
    d = days_until(opp.deadline)
    fit_score = uo.fit_score if uo else None
    breakdown = uo.score_breakdown if uo else None
    hide_percent = bool(breakdown and breakdown.get("hide_match_percent"))
    reasons = (breakdown or {}).get("reasons") or []
    if not reasons and breakdown and breakdown.get("eligibility_reasons"):
        hide_percent = hide_percent or len(breakdown.get("eligibility_reasons") or []) == 0

    fit_percent: Optional[int] = None
    if uo and fit_score is not None and not hide_percent:
        fit_percent = round(fit_score * 100)

    fit_explanation = uo.fit_explanation if uo else None
    if hide_percent and uo:
        fit_explanation = NEUTRAL_FIT_REASON

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
        fit_score=fit_score if not hide_percent else None,
        fit_percent=fit_percent,
        fit_level=uo.fit_level.value if uo and uo.fit_level else None,
        fit_explanation=fit_explanation,
        score_breakdown=breakdown,
        rank_position=uo.rank_position if uo else None,
        verification_status=opp.verification_status,
        verified_at=opp.verified_at,
        days_until_deadline=d,
        urgency_label=urgency_label(d),
    )


def _apply_sql_eligibility_filters(query, rules: dict, now: datetime):
    """Cheap eligibility predicates pushed into SQL."""
    query = query.where(
        or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
    )
    for phrase in rules.get("reject_if_text_contains") or []:
        if not phrase:
            continue
        pattern = f"%{phrase}%"
        query = query.where(
            not_(
                or_(
                    Opportunity.title.ilike(pattern),
                    Opportunity.summary.ilike(pattern),
                )
            )
        )
    require_funding = rules.get("require_funding")
    if require_funding == "full_only":
        query = query.where(
            or_(
                Opportunity.funding_type.is_(None),
                Opportunity.funding_type.notin_(("self", "partial")),
            )
        )
    return query


async def list_opportunities(
    session: AsyncSession,
    user_id: str,
    *,
    bucket: Bucket = "matches",
    sort: SortMode = "fit",
    verified_only: bool = False,
    search: Optional[str] = None,
    opportunity_type: Optional[str] = None,
    funding_type: Optional[str] = None,
    limit: int = 20,
    cursor: Optional[str] = None,
) -> OpportunityListResponse:
    from app.ingestion.eligibility import load_eligibility_rules_for_user

    now = datetime.now(timezone.utc)
    offset = int(cursor or 0)
    limit = max(1, min(limit, 100))

    profile = await session.get(UserProfile, user_id)
    eligibility_rules: dict = {}
    if profile:
        eligibility_rules = await load_eligibility_rules_for_user(session, profile.user_id)

    base = (
        select(Opportunity, UserOpportunity)
        .outerjoin(
            UserOpportunity,
            (UserOpportunity.opportunity_id == Opportunity.id) & (UserOpportunity.user_id == user_id),
        )
        .where(
            Opportunity.duplicate_of.is_(None),
            or_(
                Opportunity.verification_status.is_(None),
                Opportunity.verification_status != "stale",
            ),
        )
    )

    if verified_only:
        base = base.where(Opportunity.verification_status == "primary_confirmed")

    if search:
        base = base.where(
            or_(
                Opportunity.title.ilike(f"%{search}%"),
                Opportunity.summary.ilike(f"%{search}%"),
                Opportunity.search_vector.ilike(f"%{search.lower()}%"),
            )
        )

    if opportunity_type:
        base = base.where(Opportunity.opportunity_type == opportunity_type)

    if funding_type:
        base = base.where(Opportunity.funding_type == funding_type)

    if eligibility_rules:
        base = _apply_sql_eligibility_filters(base, eligibility_rules, now)

    week_ahead = now + timedelta(days=14)

    if bucket == "saved":
        base = base.where(UserOpportunity.status == UserOpportunityStatus.saved)
    elif bucket == "applied":
        base = base.where(UserOpportunity.status == UserOpportunityStatus.in_progress)
    elif bucket == "dismissed":
        base = base.where(UserOpportunity.status == UserOpportunityStatus.archived)
    elif bucket == "closing_soon":
        base = base.where(
            Opportunity.deadline.isnot(None),
            Opportunity.deadline <= week_ahead,
            Opportunity.deadline >= now,
        )
    else:
        base = base.where(
            or_(
                UserOpportunity.status.is_(None),
                UserOpportunity.status != UserOpportunityStatus.archived,
            )
        )

    if sort == "deadline":
        base = base.order_by(
            Opportunity.deadline.asc().nullslast(),
            UserOpportunity.rank_position.asc().nullslast(),
            Opportunity.created_at.desc(),
        )
    else:
        base = base.order_by(
            UserOpportunity.rank_position.asc().nullslast(),
            UserOpportunity.fit_score.desc().nullslast(),
            Opportunity.created_at.desc(),
        )

    count_q = select(func.count()).select_from(base.order_by(None).subquery())
    total = (await session.execute(count_q)).scalar_one()

    result = await session.execute(base.offset(offset).limit(limit))
    items = [_to_response(opp, uo) for opp, uo in result.all()]

    next_cursor: Optional[str] = None
    if offset + len(items) < total:
        next_cursor = str(offset + len(items))

    return OpportunityListResponse(items=items, total=total, next_cursor=next_cursor)


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
    from app.ingestion.eligibility import load_eligibility_rules_for_user, passes_eligibility

    query = (
        select(Opportunity, UserOpportunity)
        .outerjoin(
            UserOpportunity,
            (UserOpportunity.opportunity_id == Opportunity.id) & (UserOpportunity.user_id == user_id),
        )
        .where(
            Opportunity.duplicate_of.is_(None),
            or_(
                Opportunity.verification_status.is_(None),
                Opportunity.verification_status != "stale",
            ),
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
    profile = await session.get(UserProfile, user_id) if apply_eligibility else None
    eligibility_rules: dict = {}
    if apply_eligibility and profile:
        eligibility_rules = await load_eligibility_rules_for_user(session, profile.user_id)

    scholarships, fellowships, other = [], [], []
    now = datetime.now(timezone.utc)
    week_ahead = now + timedelta(days=7)
    tuesday = now - timedelta(days=(now.weekday() - 1) % 7)

    new_since = 0
    deadlines_week = 0

    for opp, uo in rows:
        if opp.deadline and opp.deadline.replace(tzinfo=timezone.utc) < now:
            continue
        if apply_eligibility and eligibility_rules and not passes_eligibility(opp, eligibility_rules, profile):
            continue
        resp = _to_response(opp, uo)
        if opp.created_at and opp.created_at >= tuesday:
            new_since += 1
        if opp.deadline:
            deadline = opp.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline <= week_ahead:
                deadlines_week += 1

        if opp.opportunity_type == OpportunityType.scholarship:
            scholarships.append(resp)
        elif opp.opportunity_type == OpportunityType.fellowship:
            fellowships.append(resp)
        else:
            other.append(resp)

    prep_due = await session.execute(
        select(Requirement)
        .join(UserOpportunity, Requirement.user_opportunity_id == UserOpportunity.id)
        .where(
            UserOpportunity.user_id == user_id,
            Requirement.is_completed.is_(False),
            Requirement.due_date <= week_ahead,
        )
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
        new_status = UserOpportunityStatus(status)
        append_status_history(uo, new_status)
        uo.status = new_status
    if notes is not None:
        uo.notes = notes
    await session.commit()
    await session.refresh(uo)

    if status:
        from app.services.ranking import rank_opportunities_for_user

        await rank_opportunities_for_user(session, user_id)

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
