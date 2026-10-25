"""ccrm-040 -- archived overseas students, and the overseas data-processing / document-sharing consents (agreement `kind` + v1 seed).

Revision ID: 0193_student_archive_consent
Revises: 0192_calendar_feeds

docs/superpowers/specs/2026-10-25-ccrm-040-archive-consent-design.md (DEC-SCOPE-275). 0001 builds a fresh database from the current
models, which already carry the table and the column, so each is added only when missing (0166's idiom); the seed inserts a kind only
when no overseas agreement of that kind exists. The downgrade drops the archive table (archived students reappear in the lists), the
seeded agreements with their consent records, and the column.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0193_student_archive_consent"
down_revision = "0192_calendar_feeds"
branch_labels = None
depends_on = None

# CN1: frozen here; the wording is a placeholder awaiting legal review (NEEDS_CONFIRMATION). A new version is a new active row.
SEED = {
    "data_processing": (
        "Consent to process my personal data",
        "I agree that EduSphere may collect, store and use the personal, academic, financial and identity information I or my counselor "
        "provide, to advise me and to prepare, submit and track my study-abroad applications, visa and enrolment. I can ask for a copy "
        "of my data or for it to be erased through my account.",
    ),
    "document_sharing": (
        "Consent to share my documents",
        "I agree that EduSphere may share the documents and details on my applications with the universities I apply to, visa and "
        "immigration authorities, and the partners who process my applications, only for those applications.",
    ),
}
VERSION = "v1"


def _has_table(name: str) -> bool:
    return not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    op.execute("ALTER TABLE agreements ADD COLUMN IF NOT EXISTS kind VARCHAR(30) NOT NULL DEFAULT 'enrolment'")
    if not _has_table("overseas_student_archives"):
        op.create_table(
            "overseas_student_archives",
            sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("archived_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    insert = sa.text(
        "INSERT INTO agreements (id, division, kind, version, title, body, active) "
        "SELECT :id, 'overseas', :kind, :version, :title, :body, true "
        "WHERE NOT EXISTS (SELECT 1 FROM agreements WHERE division = 'overseas' AND kind = :kind)"
    )
    for kind, (title, body) in SEED.items():
        op.execute(insert.bindparams(id=uuid.uuid4(), kind=kind, version=VERSION, title=title, body=body))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS overseas_student_archives")
    kinds = ", ".join(repr(k) for k in SEED)
    op.execute(f"DELETE FROM consent_records WHERE agreement_id IN (SELECT id FROM agreements WHERE division = 'overseas' AND kind IN ({kinds}))")
    op.execute(f"DELETE FROM agreements WHERE division = 'overseas' AND kind IN ({kinds})")
    op.execute("ALTER TABLE agreements DROP COLUMN IF EXISTS kind")
