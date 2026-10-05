"""AGN-008 -- overseas_applications.agent_student_id + submitted_on, application_deadline, offer_deadline.

Revision ID: 0057_agent_applications
Revises: 0056_agent_shortlist

docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md §4 (DEC-SCOPE-050). Four nullable columns and one
index; no existing row is read or written. `withdrawn` needs no DDL (status is String(50)). 0001 builds a fresh database from the
current models, which already carry these columns, so every add is guarded (0054's idiom). downgrade() refuses while AGN-008 data
exists rather than silently dropping it: an application of a student with no login would lose its only owner.

Re-chained 2026-10-02 on merging `main` @ `3e06381`: cut on `0054_school_onboarding_bulk`, but AGN-006's
`0055_agent_student_counseling` and AGN-007's `0056_agent_shortlist` reached `main` first, so this revision now follows 0056 (one
head). A database stamped at 0057-on-0054 is re-stamped with `alembic stamp --purge 0056_agent_shortlist` then `upgrade head` (the
guarded adds make the re-run harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0057_agent_applications"
down_revision = "0056_agent_shortlist"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
INDEX = "ix_overseas_applications_agent_student_id"
DATES = ("submitted_on", "application_deadline", "offer_deadline")


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "agent_student_id" not in existing:
        op.add_column(TABLE, sa.Column("agent_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_students.id"), nullable=True))
    for name in DATES:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, sa.Date(), nullable=True))
    indexes = set() if inspector is None else {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["agent_student_id"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE agent_student_id IS NOT NULL")).scalar():
            raise RuntimeError("Refusing to downgrade 0057_agent_applications: applications of agency students exist")
        dated = " OR ".join(f"{name} IS NOT NULL" for name in DATES)
        if bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {dated}")).scalar():
            raise RuntimeError("Refusing to downgrade 0057_agent_applications: application dates exist")
    op.drop_index(INDEX, table_name=TABLE)
    for name in reversed(DATES):
        op.drop_column(TABLE, name)
    op.drop_column(TABLE, "agent_student_id")
