from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.groq_models import GROQ_DEFAULT_CHAT_MODEL, GROQ_DEFAULT_EXTRACTION_MODEL

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PLATFORM_ENV = _BACKEND_ROOT.parent / ".env"
_DEFAULT_ENV_FILE = str(_PLATFORM_ENV) if _PLATFORM_ENV.is_file() else ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_DEFAULT_ENV_FILE, extra="ignore")

    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Optional bootstrap admin (created on startup when no users exist)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    database_url: str = "postgresql+asyncpg://career:career@localhost:5432/career_intelligence"
    database_url_sync: str = "postgresql://career:career@localhost:5432/career_intelligence"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    openai_api_key: str = ""
    tavily_api_key: str = ""

    # LLM chat — Groq (free tier) or OpenAI. Embeddings remain on OpenAI until Gemini is wired.
    llm_provider: str = ""  # "groq" | "openai" | empty (auto: groq if GROQ_API_KEY set)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_chat_model: str = GROQ_DEFAULT_CHAT_MODEL
    groq_extraction_model: str = GROQ_DEFAULT_EXTRACTION_MODEL
    llm_extraction_max_tokens: int = 2048
    llm_extraction_max_cv_chars: int = 5000
    llm_extraction_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"

    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "career@localhost"
    email_to: str = "you@example.com"

    sentry_dsn: str = ""

    # LangSmith — LLM tracing (profile CV extraction, agent chat, embeddings)
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "career-intelligence"
    langsmith_endpoint: str = ""
    langsmith_workspace_id: str = ""

    # Monorepo root — set in Docker (e.g. /workspace). Empty = auto-detect from backend layout.
    project_root: str = ""

    # Verification / trust layer (Task 2)
    verification_max_searches: int = 3
    verification_max_fetches: int = 2
    verification_batch_size: int = 25
    verification_domain_recheck_days: int = 90

    # Source health (Task 5)
    source_failure_deactivate_threshold: int = 5

    # Staleness sweep (Task 6)
    staleness_check_batch_size: int = 20
    staleness_not_seen_days: int = 14
    staleness_recrawl_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
