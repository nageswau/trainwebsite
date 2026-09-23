from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import account, admin, auth, cms, communications, employer, files, inbound, payments, portal, portfolio, public, school_skills, school_transfers, schools, student_360, workflows
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.models import Base

logger = get_logger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    if settings.auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    Path(settings.local_upload_dir).mkdir(parents=True, exist_ok=True)
    logger.info("startup_complete", extra={"extra_fields": {"environment": settings.environment}})
    yield


app = FastAPI(title="EduSphere API", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, public.router, portal.router, admin.router, admin.agents_router, files.router, workflows.router, payments.router, cms.router, communications.router, inbound.router, account.router, employer.router, schools.router, school_transfers.coordinator_router, school_transfers.admin_router, portfolio.router, school_skills.router, student_360.router):
    app.include_router(r, prefix="/api/v1")
app.mount("/local-files", StaticFiles(directory=settings.local_upload_dir, check_dir=False), name="local-files")


@app.get("/health")
async def health():
    """Liveness: process is up. Does not check dependencies."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/health/ready")
async def readiness():
    """Readiness: dependencies (database, and Redis if configured) are reachable."""
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
    try:
        from redis.asyncio import from_url as redis_from_url

        client = redis_from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            await client.ping()
            checks["redis"] = "ok"
        finally:
            await client.aclose()
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"
    healthy = all(v == "ok" for v in checks.values())
    status_code = 200 if healthy else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"status": "ok" if healthy else "degraded", "checks": checks})
