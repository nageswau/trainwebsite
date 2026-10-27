"""nehn-012 -- enquiries (created_at, id) and (owner_id) for the lead lists' date-range and counselor filters.

Revision ID: 0205_enquiry_list_indexes
Revises: 0204_certificate_workflow

docs/superpowers/specs/2026-10-27-nehn-012-lead-list-filters-export-design.md (DEC-SCOPE-298). Both indexes are new: the newest-first
lead lists and their Excel export filter on an India-time `created_at` range, and the admin list on the counselor (`owner_id`). 0001
builds a fresh database from the current models, which already carry both, so each add is guarded (0199's idiom). No row is read or
written. The downgrade drops both.
"""

import sqlalchemy as sa

from alembic import op

revision = "0205_enquiry_list_indexes"
down_revision = "0204_certificate_workflow"
branch_labels = None
depends_on = None

INDEXES = {"ix_enquiries_created": ["created_at", "id"], "ix_enquiries_owner": ["owner_id"]}


def upgrade() -> None:
    existing = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("enquiries")}
    for name, columns in INDEXES.items():
        if name not in existing:
            op.create_index(name, "enquiries", columns)


def downgrade() -> None:
    for name in INDEXES:
        op.drop_index(name, table_name="enquiries")
