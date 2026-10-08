from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import (
    account,
    admin,
    agent_applications,
    agent_dashboard,
    agent_deposits,
    agent_documents,
    agent_performance,
    agent_reports,
    agent_shortlist,
    agent_students,
    agent_tasks,
    agent_team,
    auth,
    bdm,
    bdm_activities,
    bdm_appointments,
    bdm_calendar,
    bdm_daily_reports,
    bdm_leads,
    bdm_lifecycle,
    bdm_manager_dashboard,
    bdm_meeting_requests,
    bdm_metrics,
    bdm_mous,
    bdm_my_day,
    bdm_onboarding,
    bdm_organizations,
    bdm_performance,
    bdm_pipeline,
    bdm_school_activity,
    bdm_targets,
    bdm_tasks,
    bdm_travel,
    cms,
    communications,
    employer,
    files,
    inbound,
    lead_appointments,
    lead_handover,
    lookups,
    partnership,
    partnership_universities,
    payments,
    portal,
    portfolio,
    portfolio_certificates,
    public,
    recruiter,
    recruiter_catalogue,
    recruiter_companies,
    recruiter_skills,
    school_analytics,
    school_attendance,
    school_bulk,
    school_feedback,
    school_funding,
    school_global_education,
    school_onboarding_bulk,
    school_reports,
    school_skills,
    school_student_profile,
    school_transfers,
    schools,
    student_360,
    telecaller,
    telecaller_calls,
    telecaller_catalogue,
    telecaller_content,
    telecaller_dashboard,
    telecaller_distribution,
    telecaller_follow_ups,
    telecaller_import,
    telecaller_lifecycle,
    telecaller_messages,
    telecaller_reports,
    telecaller_settings,
    telecaller_targets,
    workflows,
)
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
for r in (auth.router, public.router, portal.router, admin.router, admin.agents_router, files.router, workflows.router, agent_team.router, agent_students.router, agent_shortlist.router, agent_applications.router, agent_deposits.router, agent_deposits.admin_router, agent_documents.router, agent_tasks.router, agent_dashboard.router, agent_performance.router, agent_reports.router, lookups.router, payments.router, cms.router, communications.router, inbound.router, account.router, employer.router, schools.router, school_transfers.coordinator_router, school_transfers.admin_router, portfolio.router, portfolio_certificates.router, school_skills.router, student_360.router, school_feedback.coordinator_router, school_feedback.admin_router, school_student_profile.router, school_analytics.school_router, school_analytics.admin_router, school_global_education.router, school_reports.router, school_attendance.router, school_bulk.router, school_funding.router, school_onboarding_bulk.router, bdm.router, bdm.admin_router, bdm_organizations.router, bdm_pipeline.router, bdm_travel.router, bdm_appointments.router, bdm_activities.router, bdm_calendar.router, bdm_daily_reports.router, bdm_targets.router, bdm_my_day.router, bdm_manager_dashboard.router, bdm_tasks.router, bdm_leads.router, bdm_lifecycle.router, bdm_metrics.router, bdm_performance.router, bdm_mous.router, bdm_onboarding.router, bdm_onboarding.admin_router, bdm_school_activity.router, telecaller_distribution.router, telecaller_import.router, telecaller.router, telecaller.admin_router, telecaller_catalogue.router, telecaller_targets.router, telecaller_settings.router, telecaller_content.router, telecaller_content.public_router, telecaller_follow_ups.router, lead_appointments.telecaller_router, lead_appointments.counselor_router, lead_appointments.router, telecaller_calls.router, telecaller_dashboard.router, bdm_meeting_requests.telecaller_router, bdm_meeting_requests.router, telecaller_messages.router, lead_handover.telecaller_router, lead_handover.counselor_router, telecaller_lifecycle.router, telecaller_reports.router, recruiter.router, recruiter.admin_router, recruiter_catalogue.router, partnership.router, partnership.admin_router, recruiter_skills.router, partnership_universities.router, recruiter_companies.router):
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
