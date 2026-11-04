"""hrc-015 -- candidate documents and document requests, and the preview rendition columns of a resume.

Revision ID: 0255_candidate_documents
Revises: 0251_candidate_compensation

docs/superpowers/specs/2026-11-04-hrc-015-candidate-documents-design.md (DEC-SCOPE-379). Two new tables and two nullable columns; 0001
builds a fresh database from the current models, which already carry them, so each step runs only when missing (0222's idiom). Existing
resumes keep a null preview status (D3: a DOC/DOCX one is queued on its first preview; a PDF previews itself). The checks
are a frozen copy of the model's strings at this revision. The downgrade drops the tables and columns.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0255_candidate_documents"
down_revision = "0251_candidate_compensation"
branch_labels = None
depends_on = None

TYPES = "('certificate', 'education', 'experience_letter', 'relieving_letter', 'payslip', 'id_proof', 'other')"
DOCUMENT_CHECKS = {
    "ck_candidate_documents_type": f"document_type IN {TYPES}",
    "ck_candidate_documents_preview": "preview_status IS NULL OR preview_status IN ('pending', 'ready', 'failed')",
}
REQUEST_CHECKS = {
    "ck_candidate_document_requests_type": f"document_type IN {TYPES}",
    "ck_candidate_document_requests_status": "status IN ('pending', 'received', 'cancelled')",
}


def _uuid(name: str, *fk: sa.ForeignKey, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *fk, nullable=nullable)


def _resume_columns() -> list[sa.Column]:
    return [sa.Column("preview_status", sa.String(10), nullable=True), sa.Column("preview_key", sa.String(300), nullable=True)]


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("candidate_resumes")}
    for column in _resume_columns():
        if column.name not in existing:
            op.add_column("candidate_resumes", column)
    tables = set() if offline else set(inspector.get_table_names())
    if "candidate_document_requests" not in tables:
        op.create_table(
            "candidate_document_requests",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            _uuid("candidate_id", sa.ForeignKey("candidates.id")),
            sa.Column("document_type", sa.String(30), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(10), nullable=False),
            _uuid("requested_by_user_id", sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            _uuid("cancelled_by_user_id", sa.ForeignKey("users.id"), nullable=True),
            *(sa.CheckConstraint(sql, name=name) for name, sql in REQUEST_CHECKS.items()),
        )
        op.create_index(
            "uq_candidate_document_requests_pending", "candidate_document_requests", ["candidate_id", "document_type"], unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )  # fmt: skip
        op.create_index("ix_candidate_document_requests_candidate", "candidate_document_requests", ["candidate_id", "created_at"])
    if "candidate_documents" not in tables:
        op.create_table(
            "candidate_documents",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            _uuid("candidate_id", sa.ForeignKey("candidates.id")),
            sa.Column("document_type", sa.String(30), nullable=False),
            sa.Column("title", sa.String(120), nullable=True),
            sa.Column("storage_key", sa.String(300), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("file_name", sa.String(255), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("preview_status", sa.String(10), nullable=True),
            sa.Column("preview_key", sa.String(300), nullable=True),
            _uuid("request_id", sa.ForeignKey("candidate_document_requests.id"), nullable=True),
            _uuid("uploaded_by_user_id", sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("request_id", name="uq_candidate_documents_request"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in DOCUMENT_CHECKS.items()),
        )
        op.create_index("ix_candidate_documents_candidate", "candidate_documents", ["candidate_id", "created_at"])


def downgrade() -> None:
    op.drop_table("candidate_documents")
    op.drop_table("candidate_document_requests")
    for column in _resume_columns():
        op.drop_column("candidate_resumes", column.name)
