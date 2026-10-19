"""csc-001 -- the student -> counselor link: overseas_student_counselors.

Revision ID: 0165_overseas_student_counselors
Revises: 0164_agent_org_kyc

docs/superpowers/specs/2026-10-19-csc-001-student-counselor-link-design.md (DEC-SCOPE-226). Additive: no existing row changes. 0001 builds
a fresh database from the current models, which already carry the table, so it is created only when missing (0164's idiom). downgrade()
refuses while links exist: a counselor's caseload is not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0165_overseas_student_counselors"
down_revision = "0164_agent_org_kyc"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "overseas_student_counselors"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("counselor_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_user_id", name="uq_overseas_student_counselors_student"),
    )
    op.create_index("ix_overseas_student_counselors_counselor_user_id", TABLE, ["counselor_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0165: student-counselor links exist (csc-001)")
    op.drop_index("ix_overseas_student_counselors_counselor_user_id", table_name=TABLE)
    op.drop_table(TABLE)
