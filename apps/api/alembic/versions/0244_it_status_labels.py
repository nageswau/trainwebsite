"""itc-005 -- the IT team's status label overrides (labels, order, enable/disable of the fixed lead and lifecycle stages).

Revision ID: 0244_it_status_labels
Revises: 0243_it_conversion

docs/superpowers/specs/2026-11-03-itc-005-configurable-status-labels-design.md (S3). One new table holding override rows only (no row =
the code default), so no existing row changes and nothing is seeded. 0001 builds a fresh database from the current models, which already
carry the table, hence `IF NOT EXISTS`. The downgrade drops the table (the overrides go with it; every screen falls back to the defaults).
"""

from alembic import op

revision = "0244_it_status_labels"
down_revision = "0243_it_conversion"
branch_labels = None
depends_on = None

LABEL_MAX = 60


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS it_status_labels (
            team VARCHAR(20) NOT NULL DEFAULT 'it',
            kind VARCHAR(20) NOT NULL,
            code VARCHAR(40) NOT NULL,
            label VARCHAR({LABEL_MAX}) NOT NULL,
            sort_order INTEGER NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            updated_by_user_id UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (team, kind, code),
            CONSTRAINT ck_it_status_labels_team CHECK (team = 'it'),
            CONSTRAINT ck_it_status_labels_kind CHECK (kind IN ('lead', 'lifecycle')),
            CONSTRAINT ck_it_status_labels_label CHECK (length(label) BETWEEN 1 AND {LABEL_MAX}),
            CONSTRAINT ck_it_status_labels_sort_order CHECK (sort_order BETWEEN 0 AND 9999)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS it_status_labels")
