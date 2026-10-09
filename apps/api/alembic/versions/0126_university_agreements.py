"""upc-014 -- university_agreements + university_agreement_events + university_agreement_mou_seq: §13 MoU / agreement management.

Revision ID: 0126_university_agreements
Revises: 0125_university_comms

docs/superpowers/specs/2026-10-09-upc-014-university-agreements-design.md §2 (DEC-SCOPE-141). New tables only; no existing row changes.
0001 builds a fresh database from the current models, which already carry both tables and the sequence, so they are created only when
missing (0117's idiom). TYPES / STATUSES / EVENT_KINDS / CHECKS repeat app.models (test_upc_014_migration). downgrade() refuses while any
agreement exists: entered data is never dropped silently.

Re-chained on 2026-10-09: drafted as `0125_university_agreements` (DEC-SCOPE-140, §12BH, §2.66) on `0124_university_documents`; upc-012
(`0125_university_comms`) merged first. A database stamped at the draft is re-stamped with `alembic stamp --purge 0124_university_documents`,
then `upgrade head` (the table steps are guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0126_university_agreements"
down_revision = "0125_university_comms"
branch_labels = None
depends_on = None

AGREEMENTS = "university_agreements"
EVENTS = "university_agreement_events"
SEQ = "university_agreement_mou_seq"
UUID = postgresql.UUID(as_uuid=True)
TYPES = ("mou", "partnership_agreement", "commission_agreement")
STATUSES = ("draft", "sent", "under_review", "negotiation", "approved", "signed", "active", "renewed")
EXCLUSIVITY = ("exclusive", "non_exclusive")
EVENT_KINDS = ("create", "update", "status", "renew")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.UNIVERSITY_AGREEMENT_CHECKS
    "ck_university_agreements_type": _in("agreement_type", TYPES),
    "ck_university_agreements_status": _in("status", STATUSES),
    "ck_university_agreements_exclusivity": _in("exclusivity", EXCLUSIVITY),
    "ck_university_agreements_dates": "expiry_date > start_date",
    "ck_university_agreements_renewal_window": "renewal_date IS NULL OR (renewal_date >= start_date AND renewal_date <= expiry_date)",
    "ck_university_agreements_signed_complete": (
        "status NOT IN ('signed', 'active', 'renewed') OR (document_id IS NOT NULL AND edusphere_signatory_user_id IS NOT NULL AND "
        "edusphere_signed_on IS NOT NULL AND university_signatory_name IS NOT NULL AND university_signed_on IS NOT NULL)"
    ),
}


def fk(target: str):
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    if not op.get_context().as_sql and AGREEMENTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.execute(sa.schema.CreateSequence(sa.Sequence(SEQ)))
    op.create_table(
        AGREEMENTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mou_number", sa.String(20), nullable=False),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("agreement_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("commercial_terms", sa.Text(), nullable=True),
        sa.Column("exclusivity", sa.String(20), nullable=False),
        sa.Column("territory", sa.String(500), nullable=True),
        sa.Column("recruitment_rights", sa.Text(), nullable=True),
        sa.Column("all_courses", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("course_ids", sa.JSON(), nullable=False),
        sa.Column("country_ids", sa.JSON(), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("marketing_rights", sa.Text(), nullable=True),
        sa.Column("document_id", UUID, fk("university_documents.id"), nullable=True),
        sa.Column("edusphere_signatory_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("edusphere_signed_on", sa.Date(), nullable=True),
        sa.Column("university_signatory_name", sa.String(200), nullable=True),
        sa.Column("university_signed_on", sa.Date(), nullable=True),
        sa.Column("previous_agreement_id", UUID, fk(f"{AGREEMENTS}.id"), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("mou_number", name="uq_university_agreements_mou_number"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("uq_university_agreements_previous", AGREEMENTS, ["previous_agreement_id"], unique=True, postgresql_where=sa.text("previous_agreement_id IS NOT NULL"))
    op.create_index("ix_university_agreements_university", AGREEMENTS, ["university_id", "created_at"])
    op.create_index("ix_university_agreements_expiry", AGREEMENTS, ["status", "expiry_date"])
    op.create_table(
        EVENTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("agreement_id", UUID, fk(f"{AGREEMENTS}.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed", sa.JSON(), nullable=False),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("kind", EVENT_KINDS), name="ck_university_agreement_events_kind"),
    )
    op.create_index("ix_university_agreement_events_agreement", EVENTS, ["agreement_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {AGREEMENTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0126_university_agreements: university agreements exist. Remove them deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(AGREEMENTS)
    op.execute(sa.schema.DropSequence(sa.Sequence(SEQ)))
