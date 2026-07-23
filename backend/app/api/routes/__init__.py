from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.career_agent import approve_pending_action, create_calendar_event, run_agent
from app.database import get_db
from app.models import (
    AgentThread,
    Application,
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
    get_default_user,
    get_feed,
    get_opportunity_detail,
    get_or_create_application,
    get_weekly_focus,
    update_user_opportunity,
)
from app.services.ranking import rank_opportunities_for_user
from app.workers.ingest.tasks import fetch_all_sources_task, normalize_all_task

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@router.get("/feed", response_model=FeedResponse)
async def feed(
    search: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_default_user(db)
    return await get_feed(db, user.id, search=search, status=status)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def opportunity_detail(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    detail = await get_opportunity_detail(db, user.id, opportunity_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return detail


@router.patch("/opportunities/{opportunity_id}/status")
async def update_status(
    opportunity_id: str,
    body: UserOpportunityUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_default_user(db)
    uo = await update_user_opportunity(db, user.id, opportunity_id, body.status, body.notes)
    return {"id": uo.id, "status": uo.status.value}


@router.get("/opportunities/{opportunity_id}/calendar")
async def export_calendar(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    opp = await db.get(Opportunity, opportunity_id)
    if not opp or not opp.deadline:
        raise HTTPException(status_code=404, detail="No deadline for this opportunity")
    ics = create_calendar_event(opp.title, opp.deadline, opp.url)
    return Response(content=ics, media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="{opp.id}.ics"'})


@router.get("/opportunities/{opportunity_id}/requirements", response_model=list[RequirementResponse])
async def list_requirements(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == user.id,
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
    opportunity_id: str, body: RequirementCreate, db: AsyncSession = Depends(get_db)
):
    user = await get_default_user(db)
    uo = await update_user_opportunity(db, user.id, opportunity_id)
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
async def chat(opportunity_id: str, body: ChatRequest, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    profile_ctx = f"Goals: {user.long_term_goals}. Interests: {user.research_interests}"
    reply, citations = await answer_question(db, opportunity_id, body.message, profile_ctx)
    return ChatResponse(reply=reply, citations=citations)


@router.post("/opportunities/{opportunity_id}/agent", response_model=ChatResponse)
async def agent_chat(opportunity_id: str, body: ChatRequest, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(
        select(UserOpportunity).where(
            UserOpportunity.user_id == user.id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    uo = result.scalar_one_or_none()
    profile_data = {
        "goals": user.long_term_goals,
        "interests": user.research_interests,
        "projects": user.projects,
        "connections": user.connections,
        "universities": user.target_universities,
    }
    reply, citations, pending = await run_agent(
        db, user.id, opportunity_id, body.message, profile_data, uo.id if uo else None
    )
    return ChatResponse(reply=reply, citations=citations, pending_actions=pending)


@router.post("/agent/threads/{thread_id}/approve/{action_index}")
async def approve_action(thread_id: str, action_index: int, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await approve_pending_action(db, thread_id, action_index, user_id=user.id)
    return {"result": result}


@router.post("/opportunities/{opportunity_id}/index")
async def index_opp(opportunity_id: str, db: AsyncSession = Depends(get_db)):
    count = await index_opportunity(db, opportunity_id)
    return {"chunks_created": count}


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(db: AsyncSession = Depends(get_db)):
    return await get_default_user(db)


@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(body: UserProfileUpdate, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await rank_opportunities_for_user(db, user.id)
    await db.refresh(user)
    return user


@router.post("/profile/rank")
async def rerank(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    count = await rank_opportunities_for_user(db, user.id)
    return {"ranked": count}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    feed = await get_feed(db, user.id)

    updated = [o for o in feed.scholarships + feed.fellowships + feed.other if o.status in (None, "new")]
    in_progress = [o for o in feed.scholarships + feed.fellowships + feed.other if o.status == "in_progress"]

    learning_result = await db.execute(select(LearningItem).where(LearningItem.user_id == user.id))
    notif_result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(20)
    )

    return DashboardResponse(
        updated_cards=updated[:20],
        in_progress=in_progress,
        upskilling=learning_result.scalars().all(),
        notifications=notif_result.scalars().all(),
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def notifications(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
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
async def list_learning(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(select(LearningItem).where(LearningItem.user_id == user.id))
    return result.scalars().all()


@router.post("/learning", response_model=LearningItemResponse)
async def create_learning(body: LearningItemCreate, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    item = LearningItem(user_id=user.id, **body.model_dump())
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
async def list_people(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(select(Person).where(Person.user_id == user.id))
    return result.scalars().all()


@router.post("/people", response_model=PersonResponse)
async def create_person(body: PersonCreate, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    person = Person(user_id=user.id, **body.model_dump())
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/communities", response_model=list[CommunityResponse])
async def list_communities(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(select(Community).where(Community.user_id == user.id))
    return result.scalars().all()


@router.post("/communities", response_model=CommunityResponse)
async def create_community(body: CommunityCreate, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    community = Community(user_id=user.id, **body.model_dump())
    db.add(community)
    await db.commit()
    await db.refresh(community)
    return community


@router.get("/experiences", response_model=list[ExperienceResponse])
async def list_experiences(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    result = await db.execute(select(Experience).where(Experience.user_id == user.id))
    return result.scalars().all()


@router.post("/experiences", response_model=ExperienceResponse)
async def create_experience(body: ExperienceCreate, db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    exp = Experience(user_id=user.id, **body.model_dump())
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


@router.get("/planning/weekly", response_model=WeeklyFocusResponse)
async def weekly_focus(db: AsyncSession = Depends(get_db)):
    user = await get_default_user(db)
    return await get_weekly_focus(db, user.id)


@router.get("/sources", response_model=list[OpportunitySourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OpportunitySource))
    return result.scalars().all()


@router.post("/sources", response_model=OpportunitySourceResponse)
async def create_source(body: OpportunitySourceCreate, db: AsyncSession = Depends(get_db)):
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
async def trigger_fetch(source_id: str, db: AsyncSession = Depends(get_db)):
    result = await fetch_source(db, source_id)
    return result


@router.post("/ingest/normalize")
async def trigger_normalize(db: AsyncSession = Depends(get_db)):
    result = await normalize_raw_documents(db)
    return result


@router.post("/ingest/fetch-all")
async def trigger_fetch_all():
    fetch_all_sources_task.delay()
    return {"status": "queued"}


@router.post("/ingest/normalize-all")
async def trigger_normalize_all():
    normalize_all_task.delay()
    return {"status": "queued"}
