"""upc-026 -- university_documents + university_document_versions: the §28 document centre.

Revision ID: 0124_university_documents
Revises: 0123_candidate_consents

docs/superpowers/specs/2026-10-09-upc-026-university-documents-design.md §2 (DEC-SCOPE-139). New tables only; no existing row changes.
0001 builds a fresh database from the current models, which already carry both tables, so they are created only when missing (0117's
idiom). KINDS / DOCUMENT_CHECKS / VERSION_CHECKS repeat app.models (test_upc_026_migration). downgrade() refuses while any document exists:
entered data is never dropped silently.

Re-chained on 2026-10-09: drafted as `0123_university_documents` (DEC-SCOPE-138, §12BF, §2.64) on `0122_candidate_skills`; rec-010
(`0123_candidate_consents`) merged first. A database stamped at the draft is re-stamped with `alembic stamp --purge 0122_candidate_skills`,
then `upgrade head` (the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0124_university_documents"
down_revision = "0123_candidate_consents"
branch_labels = None
depends_on = None

DOCUMENTS = "university_documents"
VERSIONS = "university_document_versions"
UUID = postgresql.UUID(as_uuid=True)
KINDS = (
    "mou", "partnership_agreement", "commission_agreement", "brochure", "course_list", "fee_structure", "entry_requirements",
    "scholarship_information", "marketing_materials", "application_guidelines", "contact_documents", "training_documents",
)  # fmt: skip
DOCUMENT_CHECKS = {  # must equal app.models.UNIVERSITY_DOCUMENT_CHECKS
    "ck_university_documents_kind": f"kind IN ({', '.join(repr(k) for k in KINDS)})",
    "ck_university_documents_commission_internal": "kind <> 'commission_agreement' OR NOT shareable",
    "ck_university_documents_current_version": "current_version >= 1",
}
VERSION_CHECKS = {  # must equal app.models.UNIVERSITY_DOCUMENT_VERSION_CHECKS
    "ck_university_document_versions_version": "version >= 1",
    "ck_university_document_versions_size": "size_bytes > 0",
}


def fk(target: str):
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    if not op.get_context().as_sql and DOCUMENTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        DOCUMENTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("shareable", sa.Boolean(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in DOCUMENT_CHECKS.items()),
    )
    op.create_index("uq_university_documents_title", DOCUMENTS, ["university_id", "kind", sa.text("lower(title)")], unique=True)
    op.create_index("ix_university_documents_updated", DOCUMENTS, ["updated_at"])
    op.create_table(
        VERSIONS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, fk(f"{DOCUMENTS}.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_university_document_versions_version"),
        sa.UniqueConstraint("storage_key", name="uq_university_document_versions_key"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in VERSION_CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {DOCUMENTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0124_university_documents: university documents exist. Remove them deliberately first.")
    op.drop_table(VERSIONS)
    op.drop_table(DOCUMENTS)
