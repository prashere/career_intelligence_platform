from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.career_agent import approve_pending_action, create_calendar_event, run_agent
from app.api.deps import get_current_user_profile, require_admin
from app.database import get_db
from app.models import (
    Community,
    Experience,
    LearningItem,
    Notification,
    Opportunity,
    OpportunitySource,
    Person,
    Requirement,
    SourceType,
    UserOpportunity,
    UserProfile,
)
from app.rag.retriever import answer_question, index_opportunity
from app.schemas import (
    ApplicationResponse,
    ApplicationUpdate,
    ChatRequest,
    ChatResponse,
    CommunityCreate,
    CommunityResponse,
    DashboardResponse,
    ExperienceCreate,
    ExperienceResponse,
    FeedResponse,
    HealthResponse,
    LearningItemCreate,
    LearningItemResponse,
    LearningItemUpdate,
    NotificationResponse,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunitySourceCreate,
    OpportunitySourceResponse,
    PersonCreate,
    PersonResponse,
    RequirementCreate,
    RequirementResponse,
    RequirementUpdate,
    UserOpportunityUpdate,
    UserProfileResponse,
    UserProfileUpdate,
    WeeklyFocusResponse,
)
from app.services.ingestion import fetch_source, normalize_raw_documents
from app.services.opportunities import (
    empty_feed,
    get_feed,
    get_opportunity_detail,
    get_or_create_application,
    get_weekly_focus,
    list_opportunities,
    update_user_opportunity,
)
from app.services.ranking import rank_opportunities_for_user
from app.workers.ingest.tasks import fetch_all_sources_task, normalize_all_task

router = APIRouter()


async def _safe_feed(db: AsyncSession, profile_id: str, **kwargs):
    try:
        return await get_feed(db, profile_id, **kwargs)
    except ProgrammingError:
        await db.rollback()
        return empty_feed()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@router.get("/feed", response_model=FeedResponse)
async def feed(
    search: str | None = Query(None),
    status: str | None = Query(None),
    opportunity_type: str | None = Query(None),
    funding_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    # Deprecated: use GET /opportunities for ranked paginated list.
    return await _safe_feed(
        db,
        profile.id,
        search=search,
        status=status,
        opportunity_type=opportunity_type,
        funding_type=funding_type,
    )


@router.get("/opportunities", response_model=OpportunityListResponse)
async def opportunities_list(
    bucket: str = Query("matches"),
    sort: str = Query("fit"),
    verified_only: bool = Query(False),
    search: str | None = Query(None),
    opportunity_type: str | None = Query(None),
    funding_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    allowed_buckets = {"matches", "closing_soon", "saved", "applied", "dismissed"}
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail=f"Invalid bucket: {bucket}")
    if sort not in ("fit", "deadline"):
        raise HTTPException(status_code=400, detail=f"Invalid sort: {sort}")
    try:
        return await list_opportunities(
            db,
            profile.id,
            bucket=bucket,
            sort=sort,
            verified_only=verified_only,
            search=search,
            opportunity_type=opportunity_type,
            funding_type=funding_type,
            limit=limit,
            cursor=cursor,
        )
    except ProgrammingError:
        await db.rollback()
        return OpportunityListResponse(items=[], total=0, next_cursor=None)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def opportunity_detail(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    detail = await get_opportunity_detail(db, profile.id, opportunity_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return detail


@router.patch("/opportunities/{opportunity_id}/status")
async def update_status(
    opportunity_id: str,
    body: UserOpportunityUpdate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    uo = await update_user_opportunity(db, profile.id, opportunity_id, body.status, body.notes)
    return {"id": uo.id, "status": uo.status.value}


@router.get("/opportunities/{opportunity_id}/calendar")
async def export_calendar(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    opp = await db.get(Opportunity, opportunity_id)
    if not opp or not opp.deadline:
        raise HTTPException(status_code=404, detail="No deadline for this opportunity")
    ics = create_calendar_event(opp.title, opp.deadline, opp.url)
    return Response(content=ics, media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="{opp.id}.ics"'})


@router.get("/opportunities/{opportunity_id}/requirements", response_model=list[RequirementResponse])
async def list_requirements(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == profile.id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    uo = result.scalar_one_or_none()
    if not uo:
        return []
    req_result = await db.execute(select(Requirement).where(Requirement.user_opportunity_id == uo.id))
    return req_result.scalars().all()


@router.post("/opportunities/{opportunity_id}/requirements", response_model=RequirementResponse)
async def add_requirement(
    opportunity_id: str,
    body: RequirementCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    uo = await update_user_opportunity(db, profile.id, opportunity_id)
    req = Requirement(user_opportunity_id=uo.id, title=body.title, due_date=body.due_date)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


@router.patch("/requirements/{requirement_id}", response_model=RequirementResponse)
async def update_requirement(
    requirement_id: str, body: RequirementUpdate, db: AsyncSession = Depends(get_db)
):
    req = await db.get(Requirement, requirement_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(req, field, value)
    await db.commit()
    await db.refresh(req)
    return req


@router.post("/opportunities/{opportunity_id}/chat", response_model=ChatResponse)
async def chat(
    opportunity_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    profile_ctx = f"Goals: {profile.long_term_goals}. Interests: {profile.research_interests}"
    reply, citations = await answer_question(db, opportunity_id, body.message, profile_ctx)
    return ChatResponse(reply=reply, citations=citations)


@router.post("/opportunities/{opportunity_id}/agent", response_model=ChatResponse)
async def agent_chat(
    opportunity_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == profile.id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    uo = result.scalar_one_or_none()
    profile_data = {
        "goals": profile.long_term_goals,
        "interests": profile.research_interests,
        "projects": profile.projects,
        "connections": profile.connections,
        "universities": profile.target_universities,
    }
    reply, citations, pending = await run_agent(
        db, profile.id, opportunity_id, body.message, profile_data, uo.id if uo else None
    )
    return ChatResponse(reply=reply, citations=citations, pending_actions=pending)


@router.post("/agent/threads/{thread_id}/approve/{action_index}")
async def approve_action(
    thread_id: str,
    action_index: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await approve_pending_action(db, thread_id, action_index, user_id=profile.id)
    return {"result": result}


@router.post("/opportunities/{opportunity_id}/index")
async def index_opp(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    count = await index_opportunity(db, opportunity_id)
    return {"chunks_created": count}


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(profile: UserProfile = Depends(get_current_user_profile)):
    return profile


@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(
    body: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    try:
        await rank_opportunities_for_user(db, profile.id)
    except ProgrammingError:
        await db.rollback()
    await db.refresh(profile)
    return profile


@router.post("/profile/rank")
async def rerank(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    try:
        count = await rank_opportunities_for_user(db, profile.id)
    except ProgrammingError:
        await db.rollback()
        count = 0
    return {"ranked": count}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    feed = await _safe_feed(db, profile.id)

    updated = [o for o in feed.scholarships + feed.fellowships + feed.other if o.status in (None, "new")]
    in_progress = [o for o in feed.scholarships + feed.fellowships + feed.other if o.status == "in_progress"]

    try:
        learning_result = await db.execute(select(LearningItem).where(LearningItem.user_id == profile.id))
        notif_result = await db.execute(
            select(Notification)
            .where(Notification.user_id == profile.id)
            .order_by(Notification.created_at.desc())
            .limit(20)
        )
        upskilling = learning_result.scalars().all()
        notifications = notif_result.scalars().all()
    except ProgrammingError:
        await db.rollback()
        upskilling = []
        notifications = []

    return DashboardResponse(
        updated_cards=updated[:20],
        in_progress=in_progress,
        upskilling=upskilling,
        notifications=notifications,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def notifications(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(
        select(Notification).where(Notification.user_id == profile.id).order_by(Notification.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db)):
    notif = await db.get(Notification, notification_id)
    if notif:
        notif.is_read = True
        await db.commit()
    return {"ok": True}


@router.get("/applications/{user_opportunity_id}", response_model=ApplicationResponse)
async def get_application(user_opportunity_id: str, db: AsyncSession = Depends(get_db)):
    app = await get_or_create_application(db, user_opportunity_id)
    return app


@router.patch("/applications/{user_opportunity_id}", response_model=ApplicationResponse)
async def update_application(
    user_opportunity_id: str, body: ApplicationUpdate, db: AsyncSession = Depends(get_db)
):
    app = await get_or_create_application(db, user_opportunity_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(app, field, value)
    await db.commit()
    await db.refresh(app)
    return app


@router.get("/learning", response_model=list[LearningItemResponse])
async def list_learning(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(select(LearningItem).where(LearningItem.user_id == profile.id))
    return result.scalars().all()


@router.post("/learning", response_model=LearningItemResponse)
async def create_learning(
    body: LearningItemCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    item = LearningItem(user_id=profile.id, **body.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/learning/{item_id}", response_model=LearningItemResponse)
async def update_learning(item_id: str, body: LearningItemUpdate, db: AsyncSession = Depends(get_db)):
    item = await db.get(LearningItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Learning item not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/people", response_model=list[PersonResponse])
async def list_people(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(select(Person).where(Person.user_id == profile.id))
    return result.scalars().all()


@router.post("/people", response_model=PersonResponse)
async def create_person(
    body: PersonCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    person = Person(user_id=profile.id, **body.model_dump())
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/communities", response_model=list[CommunityResponse])
async def list_communities(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(select(Community).where(Community.user_id == profile.id))
    return result.scalars().all()


@router.post("/communities", response_model=CommunityResponse)
async def create_community(
    body: CommunityCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    community = Community(user_id=profile.id, **body.model_dump())
    db.add(community)
    await db.commit()
    await db.refresh(community)
    return community


@router.get("/experiences", response_model=list[ExperienceResponse])
async def list_experiences(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    result = await db.execute(select(Experience).where(Experience.user_id == profile.id))
    return result.scalars().all()


@router.post("/experiences", response_model=ExperienceResponse)
async def create_experience(
    body: ExperienceCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    exp = Experience(user_id=profile.id, **body.model_dump())
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


@router.get("/planning/weekly", response_model=WeeklyFocusResponse)
async def weekly_focus(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_user_profile),
):
    return await get_weekly_focus(db, profile.id)


@router.get("/sources", response_model=list[OpportunitySourceResponse])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _: UserProfile = Depends(require_admin),
):
    result = await db.execute(select(OpportunitySource))
    return result.scalars().all()


@router.post("/sources", response_model=OpportunitySourceResponse)
async def create_source(
    body: OpportunitySourceCreate,
    db: AsyncSession = Depends(get_db),
    _: UserProfile = Depends(require_admin),
):
    source = OpportunitySource(
        name=body.name,
        url=body.url,
        source_type=SourceType(body.source_type),
        fetch_interval_minutes=body.fetch_interval_minutes,
        parser_config=body.parser_config,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.post("/sources/{source_id}/fetch")
async def trigger_fetch(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserProfile = Depends(require_admin),
):
    result = await fetch_source(db, source_id)
    return result


@router.post("/ingest/normalize")
async def trigger_normalize(
    db: AsyncSession = Depends(get_db),
    _: UserProfile = Depends(require_admin),
):
    result = await normalize_raw_documents(db)
    return result


@router.post("/ingest/fetch-all")
async def trigger_fetch_all(_: UserProfile = Depends(require_admin)):
    fetch_all_sources_task.delay()
    return {"status": "queued"}


@router.post("/ingest/normalize-all")
async def trigger_normalize_all(_: UserProfile = Depends(require_admin)):
    normalize_all_task.delay()
    return {"status": "queued"}
