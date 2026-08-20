from typing import Optional

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


async def send_email(subject: str, body: str, to: Optional[str] = None) -> bool:
    recipient = to or settings.email_to
    if not recipient:
        return False

    if settings.resend_api_key:
        try:
            import resend

            resend.api_key = settings.resend_api_key
            resend.Emails.send(
                {
                    "from": settings.email_from,
                    "to": [recipient],
                    "subject": subject,
                    "text": body,
                }
            )
            return True
        except Exception:
            return False

    if settings.smtp_host:
        import smtplib
        from email.mime.text import MIMEText

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = settings.email_from
            msg["To"] = recipient
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception:
            return False

    return False


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via Tavily. Returns [] when unavailable so callers can
    distinguish 'no evidence found' from a fabricated placeholder result."""
    if not settings.tavily_api_key:
        logger.warning("web_search_unavailable", reason="TAVILY_API_KEY not set")
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.tavily_api_key, "query": query, "max_results": max_results},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", []) or []
    except Exception as exc:
        logger.warning("web_search_failed", query=query[:120], error=str(exc))
        return []
