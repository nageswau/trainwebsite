"""upc-008 -- Expected timeline + milestone tracker.

Revision ID: 0127_university_milestones
Revises: 0126_partnership_tasks

docs/superpowers/specs/2026-10-09-upc-008-partnership-timeline-design.md §2 (DEC-SCOPE-142). Adds the four §5 expected-timeline columns to
`universities` and the sparse `university_milestones` table. 0001 builds a fresh database from the current models, which already carry
them, so every step is guarded. CHECKS repeats app.models (test_upc_008_migration). No backfill: inventing targets would invent facts.
downgrade() refuses while any milestone or expected value exists: it would drop them.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0127_university_milestones"
down_revision = "0126_partnership_tasks"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "university_milestones"
KINDS = (
    "university_contacted", "meeting", "presentation", "proposal", "documents", "negotiation", "agreement", "signed", "onboarding",
    "student_recruitment", "first_application", "first_admission", "active_partnership",
)  # fmt: skip
CHECKS = {"ck_university_milestones_kind": f"kind IN ({', '.join(repr(k) for k in KINDS)})"}
COLUMNS = (
    ("target_partnership_date", sa.Date()),
    ("expected_intake", sa.String(80)),
    ("expected_agreement_date", sa.Date()),
    ("expected_recruitment_start", sa.Date()),
)


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns("universities")}
    for name, type_ in COLUMNS:
        if name not in present:
            op.add_column("universities", sa.Column(name, type_, nullable=True))
    if inspector is not None and TABLE in inspector.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("achieved_on", sa.Date(), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        sa.UniqueConstraint("university_id", "kind", name="uq_university_milestones_kind"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql:
        any_expected = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        found = op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} UNION ALL SELECT 1 FROM universities WHERE {any_expected} LIMIT 1")).first()
        if found:
            raise RuntimeError("Cannot downgrade 0127_university_milestones: milestones or expected timeline values exist. Remove them deliberately first.")
    op.drop_table(TABLE)
    for name, _ in reversed(COLUMNS):
        op.drop_column("universities", name)
