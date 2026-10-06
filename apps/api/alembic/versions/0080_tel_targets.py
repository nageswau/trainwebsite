"""tel-022 -- tel_targets: team defaults and per-telecaller overrides for the six EVID-019 §15 KPIs, daily and monthly, effective-dated.

Revision ID: 0080_tel_targets
Revises: 0079_bdm_mous

docs/superpowers/specs/2026-10-06-tel-022-targets-design.md §3 (DEC-SCOPE-080). Adds one table; no existing row is read or written, and nothing is seeded (the source's example values are not
defaults). 0001 builds a fresh database from the current models, which already carry the table, so creation is guarded (0075's idiom).
downgrade() refuses while any target exists: rows are the only record of what each past day's target was (T28).

Re-chained 2026-10-06 on merging `main` @ `6655e284`: drafted as `0079_tel_targets` on `0078_enquiry_lead_record` (DEC-SCOPE-078), but
bdm-005's `0079_bdm_mous` (DEC-SCOPE-078) and bdm-013 (DEC-SCOPE-079) reached `main` first, so this revision is `0080_tel_targets` after
it (one head) and the decision is DEC-SCOPE-080. Still provisional: tel-012 also chains after 0078. A database stamped at `0079_tel_targets`
is re-stamped with `alembic stamp --purge 0078_enquiry_lead_record` then `upgrade head` (the create is guarded, so the re-run is harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0080_tel_targets"
down_revision = "0079_bdm_mous"
branch_labels = None
depends_on = None

TABLE = "tel_targets"
KPIS = ("calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions")


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("team", sa.String(20), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("kpi", sa.String(40), nullable=False),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("set_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope IN ('team', 'user')", name="ck_tel_targets_scope"),
        sa.CheckConstraint(
            "(scope = 'team' AND team IS NOT NULL AND user_id IS NULL) OR (scope = 'user' AND user_id IS NOT NULL AND team IS NULL)",
            name="ck_tel_targets_subject",
        ),
        sa.CheckConstraint("period IN ('daily', 'monthly')", name="ck_tel_targets_period"),
        sa.CheckConstraint(f"kpi IN ({', '.join(repr(k) for k in KPIS)})", name="ck_tel_targets_kpi"),
        sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_targets_team"),
        sa.CheckConstraint("value IS NULL OR value BETWEEN 0 AND 100000", name="ck_tel_targets_value"),
        sa.CheckConstraint("value IS NOT NULL OR scope = 'user'", name="ck_tel_targets_value_null_user_only"),
        sa.CheckConstraint("period = 'daily' OR EXTRACT(DAY FROM effective_from) = 1", name="ck_tel_targets_monthly_first"),
    )
    op.create_index("uq_tel_targets_team", TABLE, ["team", "period", "kpi", "effective_from"], unique=True, postgresql_where=sa.text("scope = 'team'"))
    op.create_index("uq_tel_targets_user", TABLE, ["user_id", "period", "kpi", "effective_from"], unique=True, postgresql_where=sa.text("scope = 'user'"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0080_tel_targets: targets exist (the only record of past targets). Remove them deliberately first.")
    op.drop_table(TABLE)
