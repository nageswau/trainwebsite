from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, BlogPost, ContentPage, Event, GalleryItem, User

router = APIRouter(prefix="/cms", tags=["cms"])


def require_editor(user: User, division: str):
    if user.role == "super_admin":
        return
    if user.role not in {"it_admin", "overseas_admin"} or user.division != division:
        raise HTTPException(403, "CMS editor permission required")


@router.get("/pages")
async def list_pages(division: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(ContentPage).where(ContentPage.division == division, ContentPage.published.is_(True)).order_by(ContentPage.slug))).all()
    return [{"id": x.id, "slug": x.slug, "title": x.title, "body": x.body, "seo": x.seo} for x in rows]


@router.get("/manage/pages")
async def manage_pages(division: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "CMS editor permission required")
    if user.role != "super_admin":
        division = user.division
    stmt = select(ContentPage)
    if division:
        stmt = stmt.where(ContentPage.division == division)
    rows = (await db.scalars(stmt.order_by(ContentPage.division, ContentPage.slug))).all()
    return [{"id": x.id, "division": x.division, "slug": x.slug, "title": x.title, "published": x.published, "updated_at": x.updated_at} for x in rows]


@router.get("/pages/{division}/{slug}")
async def get_page(division: str, slug: str, db: AsyncSession = Depends(get_db)):
    x = await db.scalar(select(ContentPage).where(ContentPage.division == division, ContentPage.slug == slug, ContentPage.published.is_(True)))
    if not x:
        raise HTTPException(404, "Content page not found")
    return {"id": x.id, "slug": x.slug, "title": x.title, "body": x.body, "seo": x.seo}


@router.put("/pages/{division}/{slug}")
async def upsert_page(division: str, slug: str, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_editor(user, division)
    x = await db.scalar(select(ContentPage).where(ContentPage.division == division, ContentPage.slug == slug))
    if not x:
        x = ContentPage(
            division=division, slug=slug, title=payload.get("title", slug.replace("-", " ").title()), body=payload.get("body", ""), seo=payload.get("seo", {}), published=payload.get("published", True)
        )
        db.add(x)
    else:
        for k in ("title", "body", "seo", "published"):
            if k in payload:
                setattr(x, k, payload[k])
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="cms.page.upsert", entity_type="content_page", entity_id=str(x.id), metadata_json={"division": division, "slug": slug}))
    await db.commit()
    await db.refresh(x)
    return {"id": x.id, "slug": x.slug}


@router.get("/posts")
async def posts(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(BlogPost).where(BlogPost.published.is_(True))
    if division:
        stmt = stmt.where(BlogPost.division == division)
    rows = (await db.scalars(stmt.order_by(BlogPost.created_at.desc()).limit(100))).all()
    return [{"id": x.id, "division": x.division, "slug": x.slug, "title": x.title, "summary": x.summary, "category": x.category} for x in rows]


@router.get("/manage/posts")
async def manage_posts(division: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "CMS editor permission required")
    if user.role != "super_admin":
        division = user.division
    stmt = select(BlogPost)
    if division:
        stmt = stmt.where(BlogPost.division == division)
    rows = (await db.scalars(stmt.order_by(BlogPost.created_at.desc()).limit(500))).all()
    return [{"id": x.id, "division": x.division, "slug": x.slug, "title": x.title, "category": x.category, "published": x.published, "updated_at": x.updated_at} for x in rows]


@router.post("/posts", status_code=201)
async def create_post(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    division = payload["division"]
    require_editor(user, division)
    item = BlogPost(
        division=division,
        slug=payload["slug"],
        title=payload["title"],
        summary=payload.get("summary", ""),
        body=payload.get("body", ""),
        category=payload.get("category", "News"),
        published=payload.get("published", True),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="cms.post.create", entity_type="blog_post", entity_id=str(item.id), metadata_json={"division": division}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "slug": item.slug}


@router.patch("/posts/{post_id}")
async def update_post(post_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(BlogPost, post_id)
    if not item:
        raise HTTPException(404, "Post not found")
    require_editor(user, item.division)
    for key in {"slug", "title", "summary", "body", "category", "published"}:
        if key in payload:
            setattr(item, key, payload[key])
    db.add(AuditLog(user_id=user.id, action="cms.post.update", entity_type="blog_post", entity_id=str(item.id), metadata_json={"fields": list(payload)}))
    await db.commit()
    return {"id": item.id, "slug": item.slug}


@router.post("/events", status_code=201)
async def create_event(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    division = payload["division"]
    require_editor(user, division)
    from datetime import datetime

    item = Event(
        division=division,
        title=payload["title"],
        event_type=payload.get("event_type", "Seminar"),
        starts_at=datetime.fromisoformat(payload["starts_at"]),
        location=payload.get("location", "Online"),
        description=payload.get("description", ""),
        registration_url=payload.get("registration_url"),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="cms.event.create", entity_type="event", entity_id=str(item.id), metadata_json={"division": division}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id}


@router.get("/events")
async def list_events(division: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "CMS editor permission required")
    if user.role != "super_admin":
        division = user.division
    stmt = select(Event)
    if division:
        stmt = stmt.where(Event.division == division)
    rows = (await db.scalars(stmt.order_by(Event.starts_at.desc()).limit(500))).all()
    return [{"id": x.id, "division": x.division, "title": x.title, "event_type": x.event_type, "starts_at": x.starts_at, "location": x.location, "registration_url": x.registration_url} for x in rows]


@router.patch("/events/{event_id}")
async def update_event(event_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Event, event_id)
    if not item:
        raise HTTPException(404, "Event not found")
    require_editor(user, item.division)
    for key in {"title", "event_type", "location", "description", "registration_url"}:
        if key in payload:
            setattr(item, key, payload[key])
    if payload.get("starts_at"):
        from datetime import datetime

        item.starts_at = datetime.fromisoformat(payload["starts_at"])
    db.add(AuditLog(user_id=user.id, action="cms.event.update", entity_type="event", entity_id=str(item.id), metadata_json={"fields": list(payload)}))
    await db.commit()
    return {"id": item.id, "title": item.title}


# PUB-005: `GalleryItem` (public read already existed, `GET /public/gallery`) had zero
# write/manage endpoints anywhere in the codebase -- an Admin could not publish a gallery
# item at all, only seed-time direct DB inserts existed. Mirrors the `posts` pattern above
# exactly (same `require_editor` scoping, same audit-log shape).
@router.get("/manage/gallery")
async def manage_gallery(division: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "CMS editor permission required")
    if user.role != "super_admin":
        division = user.division
    stmt = select(GalleryItem)
    if division:
        stmt = stmt.where(GalleryItem.division == division)
    rows = (await db.scalars(stmt.order_by(GalleryItem.created_at.desc()).limit(500))).all()
    return [{"id": x.id, "division": x.division, "title": x.title, "image_url": x.image_url, "category": x.category, "published": x.published, "updated_at": x.updated_at} for x in rows]


@router.post("/gallery", status_code=201)
async def create_gallery_item(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    division = payload["division"]
    require_editor(user, division)
    item = GalleryItem(
        division=division,
        title=payload["title"],
        image_url=payload["image_url"],
        alt_text=payload.get("alt_text", payload["title"]),
        category=payload.get("category", "General"),
        published=payload.get("published", True),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="cms.gallery.create", entity_type="gallery_item", entity_id=str(item.id), metadata_json={"division": division}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "title": item.title}


@router.patch("/gallery/{item_id}")
async def update_gallery_item(item_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(GalleryItem, item_id)
    if not item:
        raise HTTPException(404, "Gallery item not found")
    require_editor(user, item.division)
    for key in {"title", "image_url", "alt_text", "category", "published"}:
        if key in payload:
            setattr(item, key, payload[key])
    db.add(AuditLog(user_id=user.id, action="cms.gallery.update", entity_type="gallery_item", entity_id=str(item.id), metadata_json={"fields": list(payload)}))
    await db.commit()
    return {"id": item.id, "title": item.title}
