"""itc-019 (DEC-SCOPE-345) -- trainer profiles: the trainer's own (`/it/trainer/profile`), any trainer's for the IT Admin
(`/it/trainers/{id}/profile`), and the student faculty view (`/it/student/faculty`, `/it/faculty/{id}`). API_CONTRACT.md §12IQ;
RBAC_MATRIX.md §2.245."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import TrainerProfileIn
from app.services import trainer_profiles as profiles

router = APIRouter(prefix="/it", tags=["trainer-profiles"])

OWN_ONLY = "Only a trainer has a faculty profile"
ADMIN_ONLY = "Only the IT Admin can edit another trainer's profile"
STUDENT_ONLY = "Only students have a faculty view"


async def _own(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    profiles.require_role(user, {"trainer"}, OWN_ONLY)
    return user


async def _get(db: AsyncSession, trainer: User) -> dict:
    return profiles.own_view(trainer, await profiles.load(db, trainer))


async def _put(db: AsyncSession, actor: User, trainer: User, payload: TrainerProfileIn) -> dict:
    await profiles.trainer_or_404(db, trainer.id, lock=True)
    profile = await profiles.save(db, actor, trainer, payload)
    await db.commit()
    return profiles.own_view(trainer, profile)


async def _photo(db: AsyncSession, actor: User, trainer: User, file: UploadFile | None) -> dict:
    """Store the new file first, commit, then delete the replaced one; a failed commit removes the new file instead."""
    new_key = profiles.store_photo(*await profiles.read_photo(file)) if file else None
    await profiles.trainer_or_404(db, trainer.id, lock=True)
    try:
        profile, old_key = await profiles.set_photo(db, actor, trainer, new_key)
        await db.commit()
    except Exception:
        await db.rollback()
        profiles.delete_photo(new_key)
        raise
    profiles.delete_photo(old_key)
    return profiles.own_view(trainer, profile)


@router.get("/trainer/profile")
async def get_own(user: User = Depends(_own), db: AsyncSession = Depends(get_db)):
    return await _get(db, user)


@router.put("/trainer/profile")
async def put_own(payload: TrainerProfileIn, user: User = Depends(_own), db: AsyncSession = Depends(get_db)):
    return await _put(db, user, user, payload)


@router.put("/trainer/profile/photo")
async def put_own_photo(file: UploadFile = File(...), user: User = Depends(_own), db: AsyncSession = Depends(get_db)):
    return await _photo(db, user, user, file)


@router.delete("/trainer/profile/photo")
async def delete_own_photo(user: User = Depends(_own), db: AsyncSession = Depends(get_db)):
    return await _photo(db, user, user, None)


async def _subject(trainer_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> tuple[User, User]:
    profiles.require_role(user, profiles.ADMINS, ADMIN_ONLY)
    return user, await profiles.trainer_or_404(db, trainer_id)


@router.get("/trainers/{trainer_id}/profile")
async def get_any(pair: tuple[User, User] = Depends(_subject), db: AsyncSession = Depends(get_db)):
    return await _get(db, pair[1])


@router.put("/trainers/{trainer_id}/profile")
async def put_any(payload: TrainerProfileIn, pair: tuple[User, User] = Depends(_subject), db: AsyncSession = Depends(get_db)):
    return await _put(db, *pair, payload)


@router.put("/trainers/{trainer_id}/profile/photo")
async def put_any_photo(file: UploadFile = File(...), pair: tuple[User, User] = Depends(_subject), db: AsyncSession = Depends(get_db)):
    return await _photo(db, *pair, file)


@router.delete("/trainers/{trainer_id}/profile/photo")
async def delete_any_photo(pair: tuple[User, User] = Depends(_subject), db: AsyncSession = Depends(get_db)):
    return await _photo(db, *pair, None)


@router.get("/student/faculty")
async def my_faculty(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profiles.require_role(user, {"it_student"}, STUDENT_ONLY)
    return {"items": await profiles.faculty_of(db, user)}


@router.get("/faculty/{trainer_id}")
async def faculty_member(trainer_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profiles.require_role(user, {"it_student"}, STUDENT_ONLY)
    return await profiles.faculty_member(db, user, trainer_id)
