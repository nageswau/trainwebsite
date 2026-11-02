"""itc-006 -- distribution by lead source and the team's workload strategy.

Revision ID: 0223_tel_source_workload
Revises: 0222_it_student_counselors

DEC-SCOPE-338. `tel_distribution_rules` gains `source` (one of the 13 lead sources, frozen below) and the `source` kind; `tel_settings`
gains `distribution_strategy` (every existing team keeps `round_robin`, today's behaviour). 0001 builds a fresh database from the current
models, so each column and index is added only when missing and each CHECK is dropped and re-created. The downgrade refuses while source
rules exist (they would be lost silently), else restores the tel-007 shape.
"""

from alembic import op

revision = "0223_tel_source_workload"
down_revision = "0222_it_student_counselors"
branch_labels = None
depends_on = None

SOURCES = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral",
           "exhibition_event", "bdm", "other")
RULES = "tel_distribution_rules"
SHAPE = (
    "(kind = 'product' AND product_id IS NOT NULL AND city IS NULL AND source IS NULL)"
    " OR (kind = 'city' AND city IS NOT NULL AND product_id IS NULL AND source IS NULL)"
    " OR (kind = 'source' AND source IS NOT NULL AND product_id IS NULL AND city IS NULL)"
)
OLD_SHAPE = "(kind = 'product' AND product_id IS NOT NULL AND city IS NULL) OR (kind = 'city' AND city IS NOT NULL AND product_id IS NULL)"


def _check(table: str, name: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")


def upgrade() -> None:
    op.execute(f"ALTER TABLE {RULES} ADD COLUMN IF NOT EXISTS source VARCHAR(30)")
    _check(RULES, "ck_tel_distribution_rules_kind", "kind IN ('product', 'city', 'source')")
    _check(RULES, "ck_tel_distribution_rules_shape", SHAPE)
    _check(RULES, "ck_tel_distribution_rules_source", f"source IS NULL OR source IN ({', '.join(repr(s) for s in SOURCES)})")
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_tel_distribution_rules_source ON {RULES} (team, source) WHERE kind = 'source'")
    op.execute("ALTER TABLE tel_settings ADD COLUMN IF NOT EXISTS distribution_strategy VARCHAR(20) NOT NULL DEFAULT 'round_robin'")
    _check("tel_settings", "ck_tel_settings_distribution_strategy", "distribution_strategy IN ('round_robin', 'workload')")


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM {RULES} WHERE kind = 'source') THEN
                RAISE EXCEPTION 'itc-006 downgrade refused: delete the source distribution rules first';
            END IF;
        END $$""")
    op.execute("ALTER TABLE tel_settings DROP CONSTRAINT IF EXISTS ck_tel_settings_distribution_strategy")
    op.execute("ALTER TABLE tel_settings DROP COLUMN IF EXISTS distribution_strategy")
    op.execute("DROP INDEX IF EXISTS uq_tel_distribution_rules_source")
    op.execute(f"ALTER TABLE {RULES} DROP CONSTRAINT IF EXISTS ck_tel_distribution_rules_source")
    _check(RULES, "ck_tel_distribution_rules_shape", OLD_SHAPE)
    _check(RULES, "ck_tel_distribution_rules_kind", "kind IN ('product', 'city')")
    op.execute(f"ALTER TABLE {RULES} DROP COLUMN IF EXISTS source")
