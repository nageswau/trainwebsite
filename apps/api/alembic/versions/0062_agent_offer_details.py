"""AGN-010 -- overseas_applications offer columns: offer_type, offer_date, offer_conditions, offer_document_id.

Revision ID: 0062_agent_offer_details
Revises: 0061_bdm_profiles

docs/superpowers/specs/2026-10-02-agn-010-offer-details-design.md §3 (DEC-SCOPE-056). Four nullable columns, two checks and one
foreign key; no existing row is read or written. 0001/0003 build a fresh database from the current models, which already carry
them, so every add is guarded (0057's idiom). downgrade() refuses while an offer is recorded rather than silently dropping it.

Re-chained 2026-10-02 on merging `main` @ `aad6b7c`: cut as `0060_agent_offer_details` on `0059_agent_tasks`, but AGN-013's
`0060_agent_app_enrollment` and bdm-001's `0061_bdm_profiles` reached `main` first, so this revision is now
`0062_agent_offer_details` after 0061 (one head). A database stamped at `0060_agent_offer_details` is re-stamped with
`alembic stamp --purge 0059_agent_tasks` then `upgrade head` (the guarded adds make the re-run harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0062_agent_offer_details"
down_revision = "0061_bdm_profiles"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
TYPE_CHECK = "ck_overseas_applications_offer_type"
DATED_CHECK = "ck_overseas_applications_offer_dated"
DOCUMENT_FK = "fk_overseas_applications_offer_document_id"
CHECKS = {
    TYPE_CHECK: "offer_type IS NULL OR offer_type IN ('conditional', 'unconditional')",
    DATED_CHECK: "(offer_type IS NULL) = (offer_date IS NULL)",
}


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "offer_type" not in existing:
        op.add_column(TABLE, sa.Column("offer_type", sa.String(20), nullable=True))
    if "offer_date" not in existing:
        op.add_column(TABLE, sa.Column("offer_date", sa.Date(), nullable=True))
    if "offer_conditions" not in existing:
        op.add_column(TABLE, sa.Column("offer_conditions", sa.Text(), nullable=True))
    if "offer_document_id" not in existing:
        op.add_column(TABLE, sa.Column("offer_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    foreign_keys = set() if inspector is None else {fk["name"] for fk in inspector.get_foreign_keys(TABLE)}
    if DOCUMENT_FK not in foreign_keys:
        op.create_foreign_key(DOCUMENT_FK, TABLE, "student_documents", ["offer_document_id"], ["id"], ondelete="SET NULL")
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    for name, condition in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, condition)


def downgrade() -> None:
    if not op.get_context().as_sql:
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE offer_type IS NOT NULL")).scalar():
            raise RuntimeError("Refusing to downgrade 0062_agent_offer_details: recorded offers exist")
    for name in reversed(CHECKS):
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint(DOCUMENT_FK, TABLE, type_="foreignkey")
    for name in ("offer_document_id", "offer_conditions", "offer_date", "offer_type"):
        op.drop_column(TABLE, name)
