"""upc-023 -- Expected partnerships + probability override.

Revision ID: 0143_university_probability
Revises: 0142_profile_shares

docs/superpowers/specs/2026-10-10-upc-023-expected-partnerships-design.md §3 (DEC-SCOPE-161, EX2). Adds the optional manual probability
override (0-100, with its reason) to `universities`; the stage probability itself is a constant (app.partnership_stages). 0001 builds a
fresh database from the current models, which already carry them, so every step is guarded. CHECKS repeats app.models
(test_upc_023_migration). No backfill. downgrade() refuses while any override exists: it would drop them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0143_university_probability"
down_revision = "0142_profile_shares"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_universities_probability_override": "probability_override IS NULL OR probability_override BETWEEN 0 AND 100",
    "ck_universities_probability_reason": "(probability_override IS NULL) = (probability_override_reason IS NULL)",
}
COLUMNS = (("probability_override", sa.SmallInteger()), ("probability_override_reason", sa.String(500)))


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns("universities")}
    for name, type_ in COLUMNS:
        if name not in present:
            op.add_column("universities", sa.Column(name, type_, nullable=True))
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("universities")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "universities", sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text("SELECT 1 FROM universities WHERE probability_override IS NOT NULL LIMIT 1")).first()
        if found:
            raise RuntimeError("Cannot downgrade 0143_university_probability: probability overrides exist. Remove them deliberately first.")
    for name in reversed(CHECKS):
        op.drop_constraint(name, "universities", type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column("universities", name)
