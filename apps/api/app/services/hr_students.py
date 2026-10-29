"""nehn-017 (DEC-SCOPE-310): the HR population and the document types HR may open. Functions only; never commits.

H1 (builder's default, NEEDS_CONFIRMATION OD-09): HR reads the IT students in the active placement pool -- `it_student` in the IT division,
not withdrawn from placement -- the people HR's Candidate Database section already lists, so no new person is exposed.
H2: a `ProfileDocument` opens to HR when its free-text type, trimmed and lower-cased, is on ALLOWED_TYPES; any other type stays closed."""

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import aliased

from app.models import PlacementProfile, User

HR_ROLES = frozenset({"hr_team"})
ALLOWED_TYPES = frozenset({"resume", "cv", "curriculum vitae", "portfolio", "certificate", "certificates"})


def in_pool(student, profile) -> list:
    """The pool conditions on a student (User or alias) outer-joined to their placement profile (or alias)."""
    return [student.role == "it_student", student.division == "it", or_(profile.id.is_(None), profile.withdrawn.is_(False))]


def population() -> Select:
    """The HR population's user ids (own aliases, so it never correlates with an outer query's users)."""
    student, profile = aliased(User), aliased(PlacementProfile)
    return select(student.id).outerjoin(profile, profile.student_id == student.id).where(*in_pool(student, profile))


def allowed_type(document_type: str) -> bool:
    return " ".join(document_type.split()).lower() in ALLOWED_TYPES
