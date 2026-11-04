"""hrc-024 -- candidate routing rules, the routing settings row, round-robin cursors, and system rows in the assignment history.

Revision ID: 0270_candidate_routing
Revises: 0269_match_engine

docs/superpowers/specs/2026-11-04-hrc-024-candidate-routing-design.md (DEC-SCOPE-393). Adds `candidate_routing_rules` (kind + exactly the
kind's value + recruiter, unique per kind/value/recruiter), the one-row `candidate_routing_settings` (no row = round robin, no default
recruiter) and `candidate_routing_cursors`. `candidate_assignment_history` gains the reason `route` and a nullable `changed_by_user_id`
(the system). No existing row changes. 0001 builds a fresh database from the current models, so each step runs only when missing (0251's
idiom). The downgrade deletes the `route` history rows (they have no actor) before restoring NOT NULL, then drops the three tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0270_candidate_routing"
down_revision = "0269_match_engine"
branch_labels = None
depends_on = None

KINDS = ("source", "skill_category", "location")
STRATEGIES = ("round_robin", "least_workload")
RULE_CHECKS = {
    "ck_candidate_routing_rules_kind": f"kind IN ({', '.join(repr(k) for k in KINDS)})",
    "ck_candidate_routing_rules_value": (
        "(kind = 'source') = (source_id IS NOT NULL) AND (kind = 'skill_category') = (skill_category_id IS NOT NULL)"
        " AND (kind = 'location') = (location IS NOT NULL)"
    ),
}
REASON = "ck_candidate_assignment_history_reason"
OLD_REASONS = "reason IN ('create', 'assign', 'reassign')"
NEW_REASONS = "reason IN ('create', 'assign', 'reassign', 'route')"


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "candidate_routing_rules" not in tables:
        op.create_table(
            "candidate_routing_rules",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("source_id", sa.Uuid(), sa.ForeignKey("rec_candidate_sources.id"), nullable=True),
            sa.Column("skill_category_id", sa.Uuid(), sa.ForeignKey("skill_categories.id"), nullable=True),
            sa.Column("location", sa.String(80), nullable=True),
            sa.Column("recruiter_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in RULE_CHECKS.items()),
        )
        op.create_index(
            "uq_candidate_routing_rules_rule", "candidate_routing_rules",
            ["kind", sa.text("coalesce(source_id::text, skill_category_id::text, lower(location))"), "recruiter_user_id"], unique=True,
        )  # fmt: skip
    if "candidate_routing_settings" not in tables:
        op.create_table(
            "candidate_routing_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("default_recruiter_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("strategy", sa.String(16), server_default=sa.text("'round_robin'"), nullable=False),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            *_timestamps(),
            sa.CheckConstraint("id = 1", name="ck_candidate_routing_settings_one_row"),
            sa.CheckConstraint(f"strategy IN ({', '.join(repr(s) for s in STRATEGIES)})", name="ck_candidate_routing_settings_strategy"),
        )
    if "candidate_routing_cursors" not in tables:
        op.create_table(
            "candidate_routing_cursors",
            sa.Column("group_key", sa.String(120), primary_key=True),
            sa.Column("last_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        )
    op.alter_column("candidate_assignment_history", "changed_by_user_id", existing_type=sa.Uuid(), nullable=True)
    op.execute(f"ALTER TABLE candidate_assignment_history DROP CONSTRAINT IF EXISTS {REASON}")
    op.create_check_constraint(REASON, "candidate_assignment_history", NEW_REASONS)


def downgrade() -> None:
    op.execute("DELETE FROM candidate_assignment_history WHERE reason = 'route' OR changed_by_user_id IS NULL")
    op.execute(f"ALTER TABLE candidate_assignment_history DROP CONSTRAINT IF EXISTS {REASON}")
    op.create_check_constraint(REASON, "candidate_assignment_history", OLD_REASONS)
    op.alter_column("candidate_assignment_history", "changed_by_user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("candidate_routing_cursors")
    op.drop_table("candidate_routing_settings")
    op.drop_index("uq_candidate_routing_rules_rule", table_name="candidate_routing_rules")
    op.drop_table("candidate_routing_rules")
