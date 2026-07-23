import json
from datetime import datetime, timezone
from typing import Optional

import httpx
from icalendar import Calendar, Event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentThread, Opportunity, Requirement
from app.rag.retriever import retrieve_context
from app.services.email import send_email, web_search
from app.services.embeddings import chat_completion


async def get_or_create_thread(
    session: AsyncSession, user_id: str, opportunity_id: str
) -> AgentThread:
    result = await session.execute(
        select(AgentThread).where(
            AgentThread.user_id == user_id,
            AgentThread.opportunity_id == opportunity_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        thread = AgentThread(user_id=user_id, opportunity_id=opportunity_id, messages=[])
        session.add(thread)
        await session.commit()
        await session.refresh(thread)
    return thread


async def search_opportunity_context(session: AsyncSession, opportunity_id: str, query: str) -> str:
    context, citations = await retrieve_context(session, opportunity_id, query)
    return json.dumps({"context": context, "citations": citations})


async def fetch_url(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text[:5000]
            return text
    except Exception as exc:
        return f"Failed to fetch URL: {exc}"


async def update_checklist(session: AsyncSession, user_opportunity_id: str, title: str) -> str:
    session.add(Requirement(user_opportunity_id=user_opportunity_id, title=title))
    await session.commit()
    return f"Added checklist item: {title}"


def create_calendar_event(title: str, deadline: datetime, url: str = "") -> str:
    cal = Calendar()
    event = Event()
    event.add("summary", title)
    event.add("dtstart", deadline.date())
    event.add("dtend", deadline.date())
    event.add("description", url)
    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


async def create_reminder(session: AsyncSession, user_id: str, title: str, when: datetime, body: str) -> str:
    from app.services.notifications import create_notification

    await create_notification(session, user_id, title, body, "reminder")
    await send_email(title, body)
    return f"Reminder scheduled: {title} at {when.isoformat()}"


async def find_connections(profile_data: dict, context: str) -> list[str]:
    connections = []
    for project in profile_data.get("projects", []):
        if project.lower() in context.lower():
            connections.append(f"Your project '{project}' is mentioned in related context")
    for conn in profile_data.get("connections", []):
        if conn.lower() in context.lower():
            connections.append(f"Connection '{conn}' appears relevant")
    return connections


async def run_agent(
    session: AsyncSession,
    user_id: str,
    opportunity_id: str,
    message: str,
    profile_data: dict,
    user_opportunity_id: Optional[str] = None,
) -> tuple[str, list[str], list[dict]]:
    thread = await get_or_create_thread(session, user_id, opportunity_id)
    messages = list(thread.messages or [])
    messages.append({"role": "user", "content": message})

    context, citations = await retrieve_context(session, opportunity_id, message)
    web_results = await web_search(f"{message} site:reddit.com OR application tips", max_results=3)
    web_snippets = "\n".join(
        f"- {r.get('title', '')}: {r.get('content', '')[:200]}" for r in web_results
    )

    connections = await find_connections(profile_data, context + web_snippets)

    system_prompt = (
        "You are an agentic career intelligence assistant. Use the provided context and tool results. "
        "Never invent deadlines. Cite when information comes from context. "
        "Suggest concrete next steps for preparation."
    )

    tool_summary = {
        "context_citations": citations,
        "web_results": web_snippets,
        "connections": connections,
    }

    user_prompt = (
        f"User profile: {json.dumps(profile_data)}\n\n"
        f"Opportunity context:\n{context}\n\n"
        f"Tool results:\n{json.dumps(tool_summary, indent=2)}\n\n"
        f"User message: {message}"
    )

    reply = await chat_completion(
        [
            {"role": "system", "content": system_prompt},
            *[{"role": m["role"], "content": m["content"]} for m in messages[-6:]],
            {"role": "user", "content": user_prompt},
        ]
    )

    pending_actions: list[dict] = []
    lower_msg = message.lower()
    if user_opportunity_id and any(k in lower_msg for k in ["add", "checklist", "requirement"]):
        for req in ["Motivation letter", "Letters of recommendation", "Transcripts"]:
            if req.lower() in lower_msg:
                pending_actions.append(
                    {"action": "update_checklist", "title": req, "requires_approval": True}
                )

    if any(k in lower_msg for k in ["remind", "reminder", "calendar"]):
        opp = await session.get(Opportunity, opportunity_id)
        if opp and opp.deadline:
            pending_actions.append(
                {
                    "action": "create_reminder",
                    "title": f"Deadline: {opp.title}",
                    "when": opp.deadline.isoformat(),
                    "requires_approval": True,
                }
            )

    messages.append({"role": "assistant", "content": reply})
    thread.messages = messages
    thread.pending_actions = pending_actions
    await session.commit()

    return reply, citations, pending_actions


async def approve_pending_action(
    session: AsyncSession,
    thread_id: str,
    action_index: int,
    user_opportunity_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    thread = await session.get(AgentThread, thread_id)
    if not thread or not thread.pending_actions:
        return "No pending actions"
    if action_index >= len(thread.pending_actions):
        return "Invalid action index"

    action = thread.pending_actions[action_index]
    result = "Action completed"

    if action["action"] == "update_checklist" and user_opportunity_id:
        result = await update_checklist(session, user_opportunity_id, action["title"])
    elif action["action"] == "create_reminder" and user_id:
        when = datetime.fromisoformat(action["when"])
        result = await create_reminder(session, user_id, action["title"], when, action["title"])

    thread.pending_actions.pop(action_index)
    await session.commit()
    return result
