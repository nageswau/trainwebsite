"""itc-019 (DEC-SCOPE-347): trainer profiles and the student faculty view.

A trainer edits their own profile; the IT Admin may edit any trainer's (F6). A student sees the trainers of the batches they hold an
ACTIVE enrolment in (F4) -- any other trainer is 404. `public_view` is the only serializer a student response uses: a field the trainer
hides is left out of the dict entirely (AC1), and a contact route whose channel is no longer shown or present falls back to "in_app".
The photo goes through `upload_policy` ("trainer_photo") and the PUB-025 image checks (AC2), is stored under a private prefix with a
server-made name (F5) and is only ever handed out as a short-lived signed link. Functions here never commit; audit rows carry ids and
field names only (no profile text, email or phone)."""

import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import AuditLog, Batch, Enrollment, Program, TrainerProfile, User
from app.schemas import TrainerProfileIn
from app.services import program_media
from app.services.storage import storage

PREFIX = "private/trainer-photos"
ADMINS = {"it_admin", "super_admin"}
EXTENSIONS = {program_media.PNG: "png", program_media.JPEG: "jpg", program_media.WEBP: "webp"}
FIELDS = tuple(TrainerProfileIn.model_fields)
logger = get_logger("app.trainer_profiles")


def require_role(user: User, roles: set[str], message: str) -> None:
    if user.role not in roles:
        raise HTTPException(403, message)


async def trainer_or_404(db: AsyncSession, trainer_id: uuid.UUID, *, lock: bool = False) -> User:
    """An IT trainer's user row (locked FOR UPDATE for writes, so two first saves cannot both insert the profile)."""
    stmt = select(User).where(User.id == trainer_id, User.role == "trainer")
    trainer = await db.scalar(stmt.with_for_update() if lock else stmt)
    if trainer is None:
        raise HTTPException(404, "Trainer not found")
    return trainer


def _photo_url(key: str | None) -> str | None:
    return storage.presign_download(key) if key else None


def own_view(trainer: User, profile: TrainerProfile | None) -> dict:
    """The editor's view: every field and flag, plus the account email/phone the trainer may choose to show."""
    values = TrainerProfileIn().model_dump() | ({f: getattr(profile, f) for f in FIELDS} if profile else {})
    return {"trainer_id": trainer.id, "name": trainer.full_name, **values, "account_email": trainer.email, "account_phone": trainer.phone,
            "photo_url": _photo_url(profile.photo_key if profile else None)}  # fmt: skip


def public_view(trainer: User, profile: TrainerProfile | None) -> dict:
    """What a student may see (AC1): hidden or empty fields are omitted, never sent as null."""
    view = {"trainer_id": trainer.id, "name": trainer.full_name, "designation": profile.designation if profile else None,
            "expertise": list(profile.expertise or []) if profile else [], "contact_route": "in_app"}  # fmt: skip
    if profile is None:
        return view
    shown = {
        "bio": profile.bio if profile.show_bio else None,
        "office_hours": profile.office_hours if profile.show_office_hours else None,
        "photo_url": _photo_url(profile.photo_key) if profile.show_photo else None,
        "email": trainer.email if profile.show_email else None,
        "phone": trainer.phone if profile.show_phone else None,
    }
    view |= {key: value for key, value in shown.items() if value}
    if profile.contact_route in view:  # "email" / "phone" only while that channel is actually in the response
        view["contact_route"] = profile.contact_route
    return view


async def load(db: AsyncSession, trainer: User) -> TrainerProfile | None:
    return await db.get(TrainerProfile, trainer.id, populate_existing=True)


def _audit(db: AsyncSession, actor: User, trainer: User, action: str, metadata: dict) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity_type="trainer_profile", entity_id=str(trainer.id), metadata_json=metadata))


async def save(db: AsyncSession, actor: User, trainer: User, data: TrainerProfileIn) -> TrainerProfile:
    """Replace the profile (creating it on first save). The contact route must use a channel that is shown and on the account (422)."""
    channel = {"email": (data.show_email, trainer.email), "phone": (data.show_phone, trainer.phone)}.get(data.contact_route)
    if channel and not all(channel):
        raise HTTPException(422, f"To be contacted by {data.contact_route}, show your {data.contact_route} and make sure your account has one")
    profile = await load(db, trainer)
    if profile is None:
        profile = TrainerProfile(user_id=trainer.id)
        db.add(profile)
    changed = [f for f in FIELDS if getattr(profile, f, None) != getattr(data, f)]
    for field in FIELDS:
        setattr(profile, field, getattr(data, field))
    _audit(db, actor, trainer, "trainer.profile.update", {"fields": changed})
    return profile


async def read_photo(file: UploadFile) -> tuple[bytes, str]:
    return await program_media.read_image(file, "trainer_photo")


def store_photo(data: bytes, content_type: str) -> str:
    key = f"{PREFIX}/{uuid.uuid4().hex}.{EXTENSIONS[content_type]}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("trainer_photo_store_failed")
        raise HTTPException(500, "Could not store the photo; please try again") from None
    return key


def delete_photo(key: str | None) -> None:
    """Best effort; only keys `store_photo` made."""
    if not key or not key.startswith(f"{PREFIX}/"):
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("trainer_photo_delete_failed")


async def set_photo(db: AsyncSession, actor: User, trainer: User, key: str | None) -> tuple[TrainerProfile, str | None]:
    """Point the profile at a new photo (or none); returns the profile and the key it replaced (delete it only after the commit)."""
    profile = await load(db, trainer)
    if profile is None:
        profile = TrainerProfile(user_id=trainer.id)
        db.add(profile)
    old, profile.photo_key = profile.photo_key, key
    _audit(db, actor, trainer, "trainer.profile.photo", {"removed": key is None, "replaced": old is not None})
    return profile, old


def _student_batches(student: User):
    return (
        select(Batch, Program, User, TrainerProfile)
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(User, User.id == Batch.trainer_id)
        .outerjoin(TrainerProfile, TrainerProfile.user_id == Batch.trainer_id)
        .where(Enrollment.student_id == student.id, Enrollment.status == "active")
        .order_by(Batch.start_date.desc(), Batch.name)
    )


async def faculty_of(db: AsyncSession, student: User) -> list[dict]:
    """One row per batch of the student's active enrolments; `faculty` is null when the batch has no trainer yet (E)."""
    rows = (await db.execute(_student_batches(student))).all()
    return [{"batch_id": b.id, "batch": b.name, "program": p.title, "faculty": public_view(t, tp) if t else None} for b, p, t, tp in rows]


async def faculty_member(db: AsyncSession, student: User, trainer_id: uuid.UUID) -> dict:
    """One trainer's public view -- 404 unless they teach a batch the student is actively enrolled in (−)."""
    teaches = exists().where(Enrollment.batch_id == Batch.id, Enrollment.student_id == student.id, Enrollment.status == "active")
    trainer = await db.scalar(select(User).where(User.id == trainer_id, select(Batch.id).where(Batch.trainer_id == User.id, teaches).exists()))
    if trainer is None:
        raise HTTPException(404, "Trainer not found")
    return public_view(trainer, await load(db, trainer))
