from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import FitLevel, Notification, Opportunity, UserOpportunity, UserOpportunityStatus, UserProfile
from app.services.email import send_email


async def create_notification(
    session: AsyncSession,
    user_id: str,
    title: str,
    body: str,
    notification_type: str = "info",
    related_opportunity_id: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        body=body,
        notification_type=notification_type,
        related_opportunity_id=related_opportunity_id,
    )
    session.add(notification)
    await session.commit()
    await session.refresh(notification)
    return notification


async def send_daily_digest(session: AsyncSession, user_id: str) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, UserOpportunity.opportunity_id == Opportunity.id)
        .where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.status == UserOpportunityStatus.new,
            UserOpportunity.created_at >= since,
            UserOpportunity.fit_level.in_([FitLevel.strong, FitLevel.moderate]),
        )
        .order_by(UserOpportunity.fit_score.desc())
        .limit(10)
    )
    rows = result.all()
    if not rows:
        return {"sent": False, "reason": "no new matches"}

    lines = ["New career opportunities matched to your profile:\n"]
    for uo, opp in rows:
        lines.append(f"- {opp.title} ({uo.fit_explanation or 'Relevant match'})")

    body = "\n".join(lines)
    await create_notification(session, user_id, "Daily opportunity digest", body, "digest")
    sent = await send_email("Your Career Intelligence digest", body)
    return {"sent": sent, "count": len(rows)}


async def send_deadline_reminders(session: AsyncSession, user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    windows = [7, 3, 1]
    sent_count = 0

    result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, UserOpportunity.opportunity_id == Opportunity.id)
        .where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.status == UserOpportunityStatus.in_progress,
            Opportunity.deadline.isnot(None),
        )
    )

    for uo, opp in result.all():
        deadline = opp.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        days = (deadline - now).days
        if days in windows:
            title = f"Deadline reminder: {opp.title}"
            body = f"{opp.title} deadline is in {days} day(s)."
            await create_notification(session, user_id, title, body, "deadline", opp.id)
            await send_email(title, body)
            sent_count += 1

    return {"sent": sent_count}
