"""Add webinar_registrations (PUB-004, DATA_MODEL.md §2.4 correction).

Revision ID: 0009_webinar_registrations
Revises: 0008_agreements_consent

DATA_MODEL.md §2.4 originally assumed dedicated `Webinar`/`WebinarRegistration` tables
"carried over" from the reference implementation. Building PUB-004 found the same pattern
already corrected once for PUB-001 (§2.2): no such tables exist. The existing `Event` model
already covers webinar content (division-aware, seeded with an IT-division event whose
`event_type` is literally "Webinar") -- reused as-is for listing. `Event.registration_url`
only ever pointed at an external link, so in-app registration capture genuinely did not
exist anywhere in the codebase; `webinar_registrations` is the real net-new piece.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_webinar_registrations"
down_revision = "0008_agreements_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "webinar_registrations" not in existing:
        op.create_table(
            "webinar_registrations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
            sa.Column("full_name", sa.String(160), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(40), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_webinar_registrations_event_id", "webinar_registrations", ["event_id"])
        op.create_index("ix_webinar_registrations_email", "webinar_registrations", ["email"])


def downgrade() -> None:
    op.drop_index("ix_webinar_registrations_email", table_name="webinar_registrations")
    op.drop_index("ix_webinar_registrations_event_id", table_name="webinar_registrations")
    op.drop_table("webinar_registrations")
