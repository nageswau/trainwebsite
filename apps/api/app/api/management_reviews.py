"""mgmt-032 (spec MR1-MR14): the Monthly Business Review, partners only (M2/M13: it carries finance and investments). Every route
checks the tier first; every write locks the review row, adds a management audit row and commits once here."""

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import User
from app.reporting.pdf import render_monthly_review
from app.schemas import PLAN_MONTH, MonthlyReviewOut, MonthlyReviewPage, ReviewNarrativeIn
from app.services import management_audit, management_plans
from app.services import monthly_review as svc
from app.services.management_access import require_management, require_partner_only

router = APIRouter(prefix="/management/reviews", tags=["management-reviews"])
Month = Path(pattern=PLAN_MONTH)
PDF = "application/pdf"


def _partner(user: User) -> User:
    return require_partner_only(require_management(user))


@router.get("", response_model=MonthlyReviewPage)
async def list_reviews(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every review, newest month first."""
    _partner(user)
    return await svc.reviews(db)


@router.get("/{month}", response_model=MonthlyReviewOut)
async def get_review(month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _partner(user)
    return await svc.out(db, await svc.load(db, management_plans.parse_month(month)))


@router.post("/{month}/generate", response_model=MonthlyReviewOut, responses={201: {"description": "Drafted"}})
async def generate_review(response: Response, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MR4: drafts a finished month (201) or recomputes a draft's figures, keeping its narrative (200). A final review is 409."""
    _partner(user)
    month_start = management_plans.parse_month(month)
    svc.check_finished(month_start)
    review, created = await svc.generate(db, month_start, user)
    await db.commit()
    response.status_code = 201 if created else 200
    return await svc.out(db, review)


@router.patch("/{month}", response_model=MonthlyReviewOut)
async def update_review(payload: ReviewNarrativeIn, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MR13: the §9 / §10 answers of a draft; fields left out are unchanged."""
    _partner(user)
    review = await svc.update_narrative(db, user, management_plans.parse_month(month), payload.model_dump(exclude_none=True))
    await db.commit()
    return await svc.out(db, review)


@router.post("/{month}/finalise", response_model=MonthlyReviewOut)
async def finalise_review(month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MR13/MR14: needs the three Problems answers (422); afterwards the review never changes (409) and every partner gets a link."""
    _partner(user)
    review = await svc.finalise(db, user, management_plans.parse_month(month))
    await db.commit()
    return await svc.out(db, review)


@router.get("/{month}/pdf", response_class=Response, responses={200: {"content": {PDF: {}}, "description": "The review as a PDF attachment"}})
async def review_pdf(month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MR14 / AC3: the stored review as a PDF, the same document the screen renders. Never cached: it carries finance figures."""
    _partner(user)
    review = await svc.out(db, await svc.load(db, management_plans.parse_month(month)))
    content = render_monthly_review(review)
    management_audit.record(db, user, "mgmt.review", "download", str(review["id"]))
    await db.commit()
    headers = {"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="monthly-review-{month}.pdf"'}
    return Response(content=content, media_type=PDF, headers=headers)
