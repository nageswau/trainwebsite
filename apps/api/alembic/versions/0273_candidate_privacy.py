"""hrc-035 -- candidate consent sources, the anonymised marker, the retention setting and the first `candidates.erase` holder.

Revision ID: 0273_candidate_privacy
Revises: 0269_match_engine

docs/superpowers/specs/2026-11-04-hrc-035-candidate-privacy-design.md (DEC-SCOPE-396). 0001 builds a fresh database from the current
models, which already carry the columns and table, so each step runs only when missing (0222's idiom). Every constant here is a frozen
copy of the models / rbac at this revision (test_hrc_035_migration). Backfill (K1): an existing consent row without a user came from the
website form (hrc-023 W4), one by a `candidate` user from the portal (hrc-022), the rest from a student's opt-in (rec-010); all of them
were the person's own consent. No retention row is written: no row = the rule is off. The downgrade drops what this revision added.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0273_candidate_privacy"
down_revision = "0269_match_engine"
branch_labels = None
depends_on = None

CONSENT_CHECKS = {
    "ck_candidate_consents_source": "source IS NULL OR source IN ('student', 'portal', 'website', 'manual', 'import')",
    "ck_candidate_consents_basis": "lawful_basis IS NULL OR lawful_basis IN ('consent', 'provided_for_placement')",
}
CANDIDATE_CHECKS = {
    "ck_candidates_anonymised": "(anonymised_at IS NULL) = (anonymised_reason IS NULL)",
    "ck_candidates_anonymised_reason": "anonymised_reason IS NULL OR anonymised_reason IN ('request', 'retention')",
}
RETENTION_CHECKS = {
    "ck_candidate_retention_settings_one_row": "id = 1",
    "ck_candidate_retention_settings_months": "months IS NULL OR months BETWEEN 6 AND 120",
}
SEED = (("hr_manager", "candidates", "erase"),)


def _add_missing(table: str, columns: list[sa.Column], checks: dict, offline: bool) -> bool:
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(table)}
    added = False
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)
            added = True
    present = set() if offline else {c["name"] for c in inspector.get_check_constraints(table)}
    for name, sql in checks.items():
        if name not in present:
            op.create_check_constraint(name, table, sql)
    return added


def upgrade() -> None:
    offline = op.get_context().as_sql
    added = _add_missing("candidate_consents", [sa.Column("source", sa.String(10), nullable=True), sa.Column("lawful_basis", sa.String(25), nullable=True)],
                         CONSENT_CHECKS, offline)  # fmt: skip
    if added:
        op.execute("UPDATE candidate_consents SET source = 'website' WHERE user_id IS NULL")
        op.execute("UPDATE candidate_consents c SET source = 'portal' FROM users u WHERE u.id = c.user_id AND u.role = 'candidate'")
        op.execute("UPDATE candidate_consents SET source = 'student' WHERE source IS NULL")
        op.execute("UPDATE candidate_consents SET lawful_basis = 'consent'")
    _add_missing("candidates", [sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True), sa.Column("anonymised_reason", sa.String(10), nullable=True)],
                 CANDIDATE_CHECKS, offline)  # fmt: skip
    if offline or "candidate_retention_settings" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "candidate_retention_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("months", sa.SmallInteger(), nullable=True),
            sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_run_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in RETENTION_CHECKS.items()),
        )
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE resource = 'candidates' AND action = 'erase'")
    op.drop_table("candidate_retention_settings")
    for name in CANDIDATE_CHECKS:
        op.drop_constraint(name, "candidates", type_="check")
    op.drop_column("candidates", "anonymised_reason")
    op.drop_column("candidates", "anonymised_at")
    for name in CONSENT_CHECKS:
        op.drop_constraint(name, "candidate_consents", type_="check")
    op.drop_column("candidate_consents", "lawful_basis")
    op.drop_column("candidate_consents", "source")
