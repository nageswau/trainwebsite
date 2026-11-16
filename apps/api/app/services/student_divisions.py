"""ENH-033 (DEC-SCOPE-441): which divisions a student belongs to.

`User.role` / `User.division` are the student's *active portal* -- every caller gate keeps reading them. A dual student also holds an
active `UserRoleAssignment` for the other division, so "is this person a student of division X" (a staff member opening a student,
a list, a search, a report) asks this module instead. The legacy columns still count: `_sync_role_assignment` writes a row only at
login, so a student who has never signed in may have none -- and a dual student's active pair is always one of their own rows.
"""

from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRoleAssignment

STUDENT_ROLE = {"it": "it_student", "overseas": "overseas_student"}
DIVISION_OF = {role: division for division, role in STUDENT_ROLE.items()}
DIVISION_LABEL = {"it": "IT", "overseas": "Overseas"}


def _assigned(user_id_column, division: str):
    return exists().where(
        UserRoleAssignment.user_id == user_id_column,
        UserRoleAssignment.division == division,
        UserRoleAssignment.role == STUDENT_ROLE[division],
        UserRoleAssignment.is_active.is_(True),
    )


def student_of(division: str, user=User):
    """SQL filter: `user` (the `User` entity or an alias of it) is a student of `division`."""
    return or_(and_(user.role == STUDENT_ROLE[division], user.division == division), _assigned(user.id, division))


async def is_student_of(db: AsyncSession, user: User, division: str) -> bool:
    if user.role == STUDENT_ROLE[division] and user.division == division:
        return True
    return bool(await db.scalar(select(_assigned(user.id, division))))


async def held_divisions(db: AsyncSession, user: User) -> list[str]:
    """The student divisions `user` belongs to, in a stable order (IT first)."""
    return [d for d in STUDENT_ROLE if await is_student_of(db, user, d)]


async def assignment(db: AsyncSession, user_id: UUID, division: str) -> UserRoleAssignment | None:
    """The user's student assignment row for `division`, active or not."""
    return await db.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.division == division, UserRoleAssignment.role == STUDENT_ROLE[division]))
