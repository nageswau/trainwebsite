"""ENH-029 -- school_onboarding bulk target + school_bulk_upload_rows.created_user_id.

Revision ID: 0052_school_onboarding_bulk
Revises: 0051_school_bulk_uploads

docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md §4 (DEC-SCOPE-044). Widens the target_type CHECK and adds
one nullable column (no default, no backfill); no existing row is read or written. downgrade() refuses while onboarding batches
exist rather than silently deleting that history.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0052_school_onboarding_bulk"
down_revision = "0051_school_bulk_uploads"
branch_labels = None
depends_on = None

BATCHES = "school_bulk_upload_batches"
ROWS = "school_bulk_upload_rows"
CHECK = "ck_school_bulk_upload_target_type"
BEFORE = "target_type IN ('academic_result', 'psychometric_record', 'test_prep_record', 'language_record')"
AFTER = "target_type IN ('academic_result', 'psychometric_record', 'test_prep_record', 'language_record', 'school_onboarding')"


def upgrade() -> None:
    op.drop_constraint(CHECK, BATCHES, type_="check")
    op.create_check_constraint(CHECK, BATCHES, AFTER)
    # 0001 builds a fresh database from the current models, which already carry the column (0050's guard idiom).
    offline = op.get_context().as_sql
    if offline or "created_user_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(ROWS)}:
        op.add_column(ROWS, sa.Column("created_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {BATCHES} WHERE target_type = 'school_onboarding'")).scalar()
        if count:
            raise RuntimeError(f"{count} school_onboarding bulk batches exist; refusing to downgrade 0052 and lose them")
    op.drop_column(ROWS, "created_user_id")
    op.drop_constraint(CHECK, BATCHES, type_="check")
    op.create_check_constraint(CHECK, BATCHES, BEFORE)
