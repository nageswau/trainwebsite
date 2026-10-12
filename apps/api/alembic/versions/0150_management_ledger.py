"""mgmt-004 -- management ledger: ledger_categories, ledger_entries, ledger_entry_events.

Revision ID: 0150_management_ledger
Revises: 0149_program_skills

docs/superpowers/specs/2026-10-12-mgmt-004-management-ledger-design.md §3. New tables only; no existing row changes. 0001 builds a fresh
database from the current models, which already carry these tables, so each is created only when missing (0122's idiom). The ML1
categories are seeded whenever the category table is empty, so a fresh database gets them too. downgrade() refuses while any entry
exists: entered money data is never dropped silently.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0150_management_ledger"
down_revision = "0149_program_skills"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
# Frozen copies (the model reads the live ones): app.tel_sources.TEL_SOURCES and EVID-017 §8 / §22 (ML1).
CHANNELS = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral", "exhibition_event", "bdm", "other")
FIXED = ("Office rent", "Salaries", "Internet", "Software", "Utilities", "Maintenance", "Insurance", "Other fixed costs")
VARIABLE = ("Marketing", "Travel", "Events", "Trainer payments", "Agent commissions", "University expenses", "Recruitment expenses", "School activities", "Student activities")
INCOME = ("Abroad education", "IT training", "Recruitment", "School projects", "Other")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _user(name: str, nullable: bool) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "ledger_categories" not in existing:
        op.create_table(
            "ledger_categories",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("nature", sa.String(10), nullable=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            _user("created_by_user_id", True),
            _user("updated_by_user_id", True),
            *_timestamps(),
            sa.CheckConstraint(_in("kind", ("income", "expense")), name="ck_ledger_categories_kind"),
            sa.CheckConstraint("(kind = 'expense' AND nature IN ('fixed', 'variable')) OR (kind = 'income' AND nature IS NULL)", name="ck_ledger_categories_nature"),
        )
        op.create_index("uq_ledger_categories_kind_name", "ledger_categories", ["kind", sa.text("lower(name)")], unique=True)
    if "ledger_entries" not in existing:
        op.create_table(
            "ledger_entries",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("entry_date", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("category_id", UUID, sa.ForeignKey("ledger_categories.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("vertical", sa.String(12), nullable=False),
            sa.Column("channel", sa.String(30), nullable=True),
            sa.Column("program_id", UUID, sa.ForeignKey("programs.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("batch_id", UUID, sa.ForeignKey("batches.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("status", sa.String(10), server_default=sa.text("'draft'"), nullable=False),
            sa.Column("reversal_of_id", UUID, sa.ForeignKey("ledger_entries.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("receipt_key", sa.String(255), nullable=True),
            sa.Column("receipt_content_type", sa.String(100), nullable=True),
            sa.Column("receipt_name", sa.String(255), nullable=True),
            _user("created_by_user_id", False),
            _user("updated_by_user_id", False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            _user("decided_by_user_id", True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.String(500), nullable=True),
            *_timestamps(),
            sa.CheckConstraint(_in("kind", ("income", "expense")), name="ck_ledger_entries_kind"),
            sa.CheckConstraint(_in("vertical", ("abroad", "it", "recruitment", "school", "other", "shared")), name="ck_ledger_entries_vertical"),
            sa.CheckConstraint(_in("status", ("draft", "submitted", "approved", "rejected")), name="ck_ledger_entries_status"),
            sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount"),
            sa.CheckConstraint(f"channel IS NULL OR (kind = 'expense' AND {_in('channel', CHANNELS)})", name="ck_ledger_entries_channel"),
        )
        op.create_index("ix_ledger_entries_date", "ledger_entries", ["entry_date"])
        op.create_index("ix_ledger_entries_category_date", "ledger_entries", ["category_id", "entry_date"])
        op.create_index("ix_ledger_entries_vertical_date", "ledger_entries", ["vertical", "entry_date"])
        op.create_index("ix_ledger_entries_status", "ledger_entries", ["status"])
        op.create_index("uq_ledger_entries_live_reversal", "ledger_entries", ["reversal_of_id"], unique=True, postgresql_where=sa.text("status <> 'rejected'"))
    if "ledger_entry_events" not in existing:
        op.create_table(
            "ledger_entry_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("entry_id", UUID, sa.ForeignKey("ledger_entries.id", ondelete="CASCADE"), nullable=False),
            _user("actor_user_id", False),
            sa.Column("event", sa.String(10), nullable=False),
            sa.Column("from_status", sa.String(10), nullable=True),
            sa.Column("to_status", sa.String(10), nullable=True),
            sa.Column("fields", sa.JSON(), nullable=False),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("receipt_key", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in("event", ("created", "updated", "submitted", "approved", "rejected", "reversed", "receipt")), name="ck_ledger_entry_events_event"),
        )
        op.create_index("ix_ledger_entry_events_entry", "ledger_entry_events", ["entry_id", "created_at"])
    if op.get_context().as_sql or not op.get_bind().execute(sa.text("SELECT 1 FROM ledger_categories LIMIT 1")).first():
        rows = [("expense", "fixed", n) for n in FIXED] + [("expense", "variable", n) for n in VARIABLE] + [("income", None, n) for n in INCOME]
        table = sa.table("ledger_categories", sa.column("id", UUID), sa.column("kind"), sa.column("nature"), sa.column("name"))
        op.bulk_insert(table, [{"id": uuid.uuid4(), "kind": k, "nature": n, "name": name} for k, n, name in rows])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM ledger_entries LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0150_management_ledger: ledger entries exist. Clear them deliberately first.")
    op.drop_table("ledger_entry_events")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_categories")
