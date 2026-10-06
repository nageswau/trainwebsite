"""tel-003 -- enquiries become leads: the LD-000001 Lead ID and the EVID-019 §2 fields.

Revision ID: 0078_enquiry_lead_record
Revises: 0077_bdm_tasks_followups

docs/superpowers/specs/2026-10-06-tel-003-lead-record-design.md §3 (DEC-SCOPE-077). Thirteen columns, three CHECKs, a unique Lead ID and
five indexes on `enquiries`, plus the backfill: Lead IDs oldest-first (L1), `source` folded onto the 13 §2 values with any other text kept
in `metadata_json.legacy_source` (L2), `phone_normalized` (L3) and `stage_changed_at = created_at`. 0001 builds a fresh database from the
current models, which already carry all of this, so the upgrade is guarded (0074's idiom). bdm-017's columns are not touched.
downgrade() refuses while any lead holds data a downgrade would drop; otherwise it restores each legacy source.

Re-chained 2026-10-06 on merging `main` @ `675762d3`: drafted as `0077_enquiry_lead_record` on `0076_tel_catalogue` (DEC-SCOPE-075), but
bdm-008's `0077_bdm_tasks_followups` (DEC-SCOPE-075) and tel-017 (DEC-SCOPE-076) reached `main` first, so this revision is
`0078_enquiry_lead_record` after it (one head) and the decision is DEC-SCOPE-077. A database stamped at `0077_enquiry_lead_record` is
re-stamped with `alembic stamp --purge 0076_tel_catalogue` then `upgrade head` (the change here is guarded, so the re-run is harmless).
"""

import re

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0078_enquiry_lead_record"
down_revision = "0077_bdm_tasks_followups"
branch_labels = None
depends_on = None

TABLE = "enquiries"
# Frozen copies: the model reads app/tel_sources.py and models.LEAD_CHECKS; test_tel_003_migration asserts they stay identical.
SOURCES = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral", "exhibition_event", "bdm", "other")
LEAD_CODE_DEFAULT = "'LD-' || translate(format('%6s', nextval('enquiry_lead_code_seq')), ' ', '0')"
CHECKS = {
    "ck_enquiries_source": f"source IN ({', '.join(repr(s) for s in SOURCES)})",
    "ck_enquiries_priority": "priority IN ('hot', 'warm', 'cold')",
    "ck_enquiries_passing_year": "passing_year IS NULL OR passing_year BETWEEN 1950 AND 2100",
}
INDEXES = (
    ("ix_enquiries_telecaller_status", ["telecaller_user_id", "status"]),
    ("ix_enquiries_phone_normalized", ["phone_normalized"]),
    ("ix_enquiries_email_lower", [sa.text("lower(email)")]),
    ("ix_enquiries_campaign", ["campaign_id"]),
    ("ix_enquiries_product", ["product_id"]),
)
# Columns a downgrade drops that carry data of their own (lead_code, phone_normalized and stage_changed_at are derived).
OWN_DATA = ("whatsapp_number", "city", "state", "qualification", "passing_year", "institution", "product_id", "campaign_id", "telecaller_user_id")
BATCH = 1000

# Frozen copy of app/notifications/phone.normalise_phone (ENH-014) as of this revision.
_SEPARATORS = re.compile(r"[\s\-().]")
_INTERNATIONAL = re.compile(r"\+[0-9]{8,15}")
_INDIAN_MOBILE = re.compile(r"(?:0|91)?([6-9][0-9]{9})")


def _normalise_phone(raw):
    if not raw:
        return None
    compact = _SEPARATORS.sub("", raw)
    if _INTERNATIONAL.fullmatch(compact):
        return compact
    match = _INDIAN_MOBILE.fullmatch(compact)
    return f"+91{match.group(1)}" if match else None


def _backfill_phones(bind) -> None:
    """Batched by id; ids only, never a phone, in anything logged."""
    after = None
    while True:
        rows = bind.execute(sa.text(
            f"SELECT id, phone FROM {TABLE} WHERE phone IS NOT NULL" + (" AND id > :after" if after else "") + " ORDER BY id LIMIT :n"),
            {"after": after, "n": BATCH} if after else {"n": BATCH}).fetchall()
        if not rows:
            return
        updates = [{"id": r.id, "p": p} for r in rows if (p := _normalise_phone(r.phone))]
        if updates:
            bind.execute(sa.text(f"UPDATE {TABLE} SET phone_normalized = :p WHERE id = :id"), updates)
        after = rows[-1].id


def upgrade() -> None:
    if not op.get_context().as_sql and "lead_code" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}:
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.execute("CREATE SEQUENCE IF NOT EXISTS enquiry_lead_code_seq")
    op.add_column(TABLE, sa.Column("lead_code", sa.String(20), nullable=True))
    op.add_column(TABLE, sa.Column("phone_normalized", sa.String(20), nullable=True))
    op.add_column(TABLE, sa.Column("whatsapp_number", sa.String(40), nullable=True))
    op.add_column(TABLE, sa.Column("city", sa.String(120), nullable=True))
    op.add_column(TABLE, sa.Column("state", sa.String(120), nullable=True))
    op.add_column(TABLE, sa.Column("qualification", sa.String(120), nullable=True))
    op.add_column(TABLE, sa.Column("passing_year", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("institution", sa.String(200), nullable=True))
    op.add_column(TABLE, sa.Column("product_id", uuid, sa.ForeignKey("tel_products.id"), nullable=True))
    op.add_column(TABLE, sa.Column("campaign_id", uuid, sa.ForeignKey("tel_campaigns.id"), nullable=True))
    op.add_column(TABLE, sa.Column("telecaller_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column(TABLE, sa.Column("priority", sa.String(10), server_default=sa.text("'warm'"), nullable=False))
    op.add_column(TABLE, sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))

    # L2: fold case and spaces first; anything still outside the list becomes 'other', keeping the original text.
    known = ", ".join(repr(s) for s in SOURCES)
    op.execute(f"UPDATE {TABLE} SET source = lower(btrim(source)) WHERE lower(btrim(source)) IN ({known}) AND source <> lower(btrim(source))")
    op.execute(
        f"UPDATE {TABLE} SET metadata_json = (COALESCE(metadata_json::jsonb, '{{}}'::jsonb) || jsonb_build_object('legacy_source', source))::json, "
        f"source = 'other' WHERE source IS NULL OR source NOT IN ({known})"
    )
    # L1: oldest first, then the sequence continues after the last backfilled number.
    op.execute(
        f"UPDATE {TABLE} e SET lead_code = 'LD-' || translate(format('%6s', o.n), ' ', '0') "
        f"FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS n FROM {TABLE}) o WHERE o.id = e.id"
    )
    op.execute(f"SELECT setval('enquiry_lead_code_seq', COALESCE((SELECT count(*) FROM {TABLE}), 0) + 1, false)")
    op.execute(f"UPDATE {TABLE} SET stage_changed_at = created_at")
    if not op.get_context().as_sql:
        _backfill_phones(op.get_bind())

    op.alter_column(TABLE, "lead_code", nullable=False, server_default=sa.text(LEAD_CODE_DEFAULT))
    op.alter_column(TABLE, "stage_changed_at", nullable=False, server_default=sa.func.now())
    for name, sql in CHECKS.items():
        op.create_check_constraint(name, TABLE, sql)
    op.create_unique_constraint("uq_enquiries_lead_code", TABLE, ["lead_code"])
    for name, columns in INDEXES:
        op.create_index(name, TABLE, columns)


def downgrade() -> None:
    if not op.get_context().as_sql:
        own = " OR ".join(f"{c} IS NOT NULL" for c in OWN_DATA)
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE {own} OR priority <> 'warm' LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0078_enquiry_lead_record: lead data exists (assignment, product, campaign, contact details "
                               "or priority). Clear it deliberately first.")
    for name, _ in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_constraint("uq_enquiries_lead_code", TABLE, type_="unique")
    for name in reversed(CHECKS):
        op.drop_constraint(name, TABLE, type_="check")
    # after the source CHECK is gone: put each legacy text back (L2)
    op.execute(
        f"UPDATE {TABLE} SET source = metadata_json::jsonb ->> 'legacy_source', metadata_json = (metadata_json::jsonb - 'legacy_source')::json "
        "WHERE metadata_json::jsonb ? 'legacy_source'"
    )
    for column in ("stage_changed_at", "priority", "telecaller_user_id", "campaign_id", "product_id", "institution", "passing_year",
                   "qualification", "state", "city", "whatsapp_number", "phone_normalized", "lead_code"):
        op.drop_column(TABLE, column)
    op.execute("DROP SEQUENCE IF EXISTS enquiry_lead_code_seq")
