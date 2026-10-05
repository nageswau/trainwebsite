"""bdm-017 -- enquiries: BDM attribution and the explicit conversion link.

Revision ID: 0072_enquiry_bdm_attribution
Revises: 0071_bdm_activities

docs/superpowers/specs/2026-10-05-bdm-017-lead-attribution-design.md §3 (DEC-SCOPE-070). Additive: five nullable columns, two
CHECKs, one index and one partial unique index on `enquiries`; every existing row stays NULL (website and manual enquiries are
unattributed). 0001 builds a fresh database from the current models, which already carry the columns, so the change is guarded
(0061's idiom). downgrade() refuses while any row is attributed or converted: dropping the columns would silently lose that link.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0072_enquiry_bdm_attribution"
down_revision = "0071_bdm_activities"
branch_labels = None
depends_on = None

TABLE = "enquiries"


def upgrade() -> None:
    if not op.get_context().as_sql and "bdm_organization_id" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}:
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(TABLE, sa.Column("bdm_organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True))
    op.add_column(TABLE, sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column(TABLE, sa.Column("converted_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column(TABLE, sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("converted_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.create_check_constraint("ck_enquiries_bdm_attribution", TABLE, "(bdm_organization_id IS NULL) = (bdm_user_id IS NULL)")
    op.create_check_constraint(
        "ck_enquiries_conversion", TABLE,
        "(converted_user_id IS NULL) = (converted_at IS NULL) AND (converted_user_id IS NULL) = (converted_by_user_id IS NULL)",
    )
    op.create_index("ix_enquiries_bdm_org_created", TABLE, ["bdm_organization_id", "created_at"])
    op.create_index("uq_enquiries_converted_user", TABLE, ["converted_user_id"], unique=True,
                    postgresql_where=sa.text("converted_user_id IS NOT NULL"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(
            f"SELECT 1 FROM {TABLE} WHERE bdm_organization_id IS NOT NULL OR converted_user_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0072_enquiry_bdm_attribution: leads are attributed or converted. Clear them deliberately first.")
    op.drop_index("uq_enquiries_converted_user", table_name=TABLE)
    op.drop_index("ix_enquiries_bdm_org_created", table_name=TABLE)
    op.drop_constraint("ck_enquiries_conversion", TABLE, type_="check")
    op.drop_constraint("ck_enquiries_bdm_attribution", TABLE, type_="check")
    for column in ("converted_by_user_id", "converted_at", "converted_user_id", "bdm_user_id", "bdm_organization_id"):
        op.drop_column(TABLE, column)
