"""pob-025 -- the replacement guarantee: `guarantee_days` on the contract and the requirement; the placement's guarantee snapshot, expiry
alert marker, early dropout and replacement link (DEC-SCOPE-436 G1/G2/G4/G6/G7/G10).

Revision ID: 0317_placement_guarantee
Revises: 0316_placement_surveys

docs/superpowers/specs/2026-11-08-pob-025-replacement-guarantee-design.md. Additive only. 0001 builds a fresh database from the current models,
which already carry these columns, so each table's step runs only when its columns are missing. The CHECK strings are frozen copies of
`models.JOB_GUARANTEE_CHECKS`, `RECRUITER_CONTRACT_GUARANTEE_CHECKS` and `PLACEMENT_GUARANTEE_CHECKS`. No backfill: existing placements have no
structured guarantee. The downgrade drops what the upgrade added.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0317_placement_guarantee"
down_revision = "0316_placement_surveys"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JOB_CHECKS = {"ck_jobs_guarantee_days": "guarantee_days IS NULL OR guarantee_days BETWEEN 1 AND 365"}
CONTRACT_CHECKS = {"ck_recruiter_contracts_guarantee_days": "guarantee_days IS NULL OR guarantee_days BETWEEN 1 AND 365"}
PLACEMENT_CHECKS = {
    "ck_placements_guarantee": "(guarantee_days IS NULL) = (guarantee_end_date IS NULL) AND (guarantee_days IS NULL OR guarantee_days BETWEEN 1 AND 365)",
    "ck_placements_dropout": "(dropout_on IS NULL) = (dropout_reason IS NULL)",
    "ck_placements_replacement": "(replacement_job_id IS NULL AND replaced_by_placement_id IS NULL) OR dropout_on IS NOT NULL",
    "ck_placements_not_self_replaced": "replaced_by_placement_id IS NULL OR replaced_by_placement_id <> id",
}
PLACEMENT_COLUMNS = (
    "guarantee_days", "guarantee_end_date", "guarantee_alerted_at", "dropout_on", "dropout_reason", "replacement_job_id", "replaced_by_placement_id",
)  # fmt: skip


def _missing(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return True
    return column not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, checks in (("jobs", JOB_CHECKS), ("recruiter_contracts", CONTRACT_CHECKS)):
        if _missing(table, "guarantee_days"):
            op.add_column(table, sa.Column("guarantee_days", sa.Integer(), nullable=True))
            for name, sql in checks.items():
                op.create_check_constraint(name, table, sql)
    if _missing("placements", "guarantee_days"):
        op.add_column("placements", sa.Column("guarantee_days", sa.Integer(), nullable=True))
        op.add_column("placements", sa.Column("guarantee_end_date", sa.Date(), nullable=True))
        op.add_column("placements", sa.Column("guarantee_alerted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("placements", sa.Column("dropout_on", sa.Date(), nullable=True))
        op.add_column("placements", sa.Column("dropout_reason", sa.String(500), nullable=True))
        op.add_column("placements", sa.Column("replacement_job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True))
        op.add_column("placements", sa.Column("replaced_by_placement_id", UUID, sa.ForeignKey("placements.id", ondelete="RESTRICT"), nullable=True))
        op.create_unique_constraint("uq_placements_replaced_by", "placements", ["replaced_by_placement_id"])
        op.create_index("ix_placements_guarantee_end_date", "placements", ["guarantee_end_date"])
        op.create_index("ix_placements_replacement_job", "placements", ["replacement_job_id"])
        for name, sql in PLACEMENT_CHECKS.items():
            op.create_check_constraint(name, "placements", sql)


def downgrade() -> None:
    op.drop_index("ix_placements_replacement_job", table_name="placements")
    op.drop_index("ix_placements_guarantee_end_date", table_name="placements")
    op.drop_constraint("uq_placements_replaced_by", "placements", type_="unique")
    for name in PLACEMENT_CHECKS:
        op.drop_constraint(name, "placements", type_="check")
    for column in reversed(PLACEMENT_COLUMNS):
        op.drop_column("placements", column)
    for table, checks in (("recruiter_contracts", CONTRACT_CHECKS), ("jobs", JOB_CHECKS)):
        for name in checks:
            op.drop_constraint(name, table, type_="check")
        op.drop_column(table, "guarantee_days")
