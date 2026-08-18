from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.profile_intake import router as intake_router
from app.config import settings
from app.database import async_session
from app.logging_config import configure_logging, get_logger
from app.startup import run_startup_tasks
from app.telemetry.langsmith import configure_langsmith

configure_logging()
configure_langsmith()

logger = get_logger()

app = FastAPI(
    title="Career Intelligence System",
    description="Personal career intelligence companion for discovering and acting on opportunities",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(intake_router, prefix="/api/v1")


@app.on_event("startup")
async def startup():
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(dsn=settings.sentry_dsn, integrations=[FastApiIntegration()])

    if settings.app_env != "test":
        async with async_session() as session:
            await run_startup_tasks(session)

    logger.info("startup_complete", env=settings.app_env)


@app.get("/")
async def root():
    return {"message": "Career Intelligence System API", "docs": "/docs"}
