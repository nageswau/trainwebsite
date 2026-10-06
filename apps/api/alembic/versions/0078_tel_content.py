"""tel-012 -- tel_scripts, tel_assets, tel_message_templates (seeded with the EVID-019 §11/§12 kinds and the §6 example script).

Revision ID: 0078_tel_content
Revises: 0077_bdm_tasks_followups

docs/superpowers/specs/2026-10-06-tel-012-content-library-design.md §3 (DEC-SCOPE-076). Adds three tables; no existing row is written.
0001 builds a fresh database from the current models, which already carry the tables, so creation is guarded (0076's idiom) -- but the
seed always runs and inserts only what is missing, so it is idempotent and never overwrites a manager's edit. The kinds are a frozen
copy (app/tel_content_kinds.py is the live one). downgrade() refuses while manager data exists: any asset, or any template/script that
is not an untouched seed row.
"""

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0078_tel_content"
down_revision = "0077_bdm_tasks_followups"
branch_labels = None
depends_on = None

WHATSAPP_KINDS = ("welcome", "course_details", "brochure", "fee_details", "counselling_appointment", "reminder", "follow_up", "overseas_destination", "document_request")
EMAIL_KINDS = ("course_brochure", "fee_proposal", "counselling_confirmation", "overseas_information", "university_information", "follow_up", "appointment_confirmation")

# C4: one generic (no product) template per kind, neutral wording the manager edits. No seed uses {brochure_link}: that placeholder
# needs a brochure attached, and none exists yet.
_SIGN = "\n\nRegards,\nEduSphere"
SEED = (
    ("whatsapp", "welcome", "Welcome message", None, "Hi {name}, thank you for contacting EduSphere about {product}. I'm your EduSphere advisor and I'll help you with the next steps."),
    ("whatsapp", "course_details", "Course details", None, "Hi {name}, here are the details of {product}. Let me know a good time to talk and I'll answer your questions."),
    ("whatsapp", "brochure", "Brochure", None, "Hi {name}, thank you for your interest in {product}. Reply here and I'll share the brochure with you."),
    ("whatsapp", "fee_details", "Fee details", None, "Hi {name}, thank you for asking about the fees for {product}. I'll share the fee details and payment options with you."),
    ("whatsapp", "counselling_appointment", "Counselling appointment", None, "Hi {name}, your counselling session for {product} is booked for {appointment_time}. Reply here if you need to change it."),
    ("whatsapp", "reminder", "Reminder", None, "Hi {name}, a reminder of your EduSphere appointment at {appointment_time}."),
    ("whatsapp", "follow_up", "Follow-up", None, "Hi {name}, I'm following up on your interest in {product}. Is now a good time to talk?"),
    ("whatsapp", "overseas_destination", "Overseas destination information", None, "Hi {name}, here is some information about studying in {product}. I'm happy to answer your questions about universities, costs and visas."),
    ("whatsapp", "document_request", "Document request", None, "Hi {name}, to move forward with {product}, please share your documents. I'll send you the list."),
    ("email", "course_brochure", "Course brochure", "{product} course brochure", "Dear {name},\n\nThank you for your interest in {product}. Reply to this email and we will send you the course brochure." + _SIGN),
    ("email", "fee_proposal", "Fee proposal", "{product} fee proposal", "Dear {name},\n\nThank you for your interest in {product}. Our fee proposal and payment options follow below." + _SIGN),
    ("email", "counselling_confirmation", "Counselling confirmation", "Your counselling session is confirmed", "Dear {name},\n\nYour counselling session about {product} is confirmed for {appointment_time}." + _SIGN),
    ("email", "overseas_information", "Overseas information", "Studying in {product}", "Dear {name},\n\nThank you for your interest in studying in {product}. Here is an overview of the options we can help you with." + _SIGN),
    ("email", "university_information", "University information", "University options for {product}", "Dear {name},\n\nHere are university options that match your interest in {product}." + _SIGN),
    ("email", "follow_up", "Follow-up email", "Following up on {product}", "Dear {name},\n\nI'm following up on your interest in {product}. Reply to this email with a good time to talk." + _SIGN),
    ("email", "appointment_confirmation", "Appointment confirmation", "Appointment confirmed for {appointment_time}", "Dear {name},\n\nYour appointment with EduSphere is confirmed for {appointment_time}." + _SIGN),
)
SEED_NAMES = tuple(row[2] for row in SEED)
SCRIPT_NAME = "Cyber Security standard script"
# EVID-019 §6, in source order.
SCRIPT_STEPS = [
    {"title": title, "notes": None}
    for title in ("Introduction", "Understand qualification", "Ask career goal", "Explain course", "Check availability", "Fix counselling appointment", "Assign counselor")
]


def _in(values) -> str:
    return ", ".join(repr(v) for v in values)


def seed_statements():
    """One INSERT per template, skipped when that (channel, lower(name)) exists; one for the script, skipped when the IT product
    "Cyber Security" is missing (renamed) or already has a script."""
    template = (  # explicit casts: each parameter is used twice, and asyncpg refuses a type it deduces differently per use
        "INSERT INTO tel_message_templates (id, channel, kind, name, subject, body) "
        "SELECT CAST(:id AS uuid), CAST(:channel AS varchar), CAST(:kind AS varchar), CAST(:name AS varchar), CAST(:subject AS varchar), CAST(:body AS text) "
        "WHERE NOT EXISTS (SELECT 1 FROM tel_message_templates WHERE channel = CAST(:channel AS varchar) AND lower(name) = lower(CAST(:name AS varchar)))"
    )
    statements = [(template, {"id": uuid.uuid4(), "channel": c, "kind": k, "name": n, "subject": s, "body": b}) for c, k, n, s, b in SEED]
    script = (
        "INSERT INTO tel_scripts (id, product_id, name, steps) SELECT CAST(:id AS uuid), p.id, CAST(:name AS varchar), CAST(:steps AS json) "
        "FROM tel_products p WHERE p.product_group = 'it' AND lower(p.name) = 'cyber security' "
        "AND NOT EXISTS (SELECT 1 FROM tel_scripts s WHERE s.product_id = p.id)"
    )
    statements.append((script, {"id": uuid.uuid4(), "name": SCRIPT_NAME, "steps": json.dumps(SCRIPT_STEPS)}))
    return statements


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if op.get_context().as_sql or "tel_scripts" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "tel_scripts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_products.id"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            *_timestamps(),
        )
        op.create_index("uq_tel_scripts_active_product", "tel_scripts", ["product_id"], unique=True, postgresql_where=sa.text("active"))
        op.create_table(
            "tel_assets",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_products.id"), nullable=True),
            sa.Column("storage_key", sa.String(255), nullable=False),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            *_timestamps(),
            sa.CheckConstraint("kind IN ('brochure', 'fee')", name="ck_tel_assets_kind"),
        )
        op.create_index("uq_tel_assets_storage_key", "tel_assets", ["storage_key"], unique=True)
        op.create_table(
            "tel_message_templates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_products.id"), nullable=True),
            sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_assets.id"), nullable=True),
            sa.Column("subject", sa.String(200), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            *_timestamps(),
            sa.CheckConstraint("channel IN ('whatsapp', 'email')", name="ck_tel_message_templates_channel"),
            sa.CheckConstraint(
                f"(channel = 'whatsapp' AND kind IN ({_in(WHATSAPP_KINDS)})) OR (channel = 'email' AND kind IN ({_in(EMAIL_KINDS)}))",
                name="ck_tel_message_templates_kind",
            ),
            sa.CheckConstraint("(channel = 'email') = (subject IS NOT NULL)", name="ck_tel_message_templates_subject"),
        )
        op.create_index("uq_tel_message_templates_channel_name", "tel_message_templates", ["channel", sa.text("lower(name)")], unique=True)
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


def _manager_data(bind) -> bool:
    if bind.execute(sa.text("SELECT 1 FROM tel_assets LIMIT 1")).first():
        return True
    seeded = sa.text(
        "SELECT count(*) FROM tel_message_templates t WHERE t.product_id IS NULL AND t.asset_id IS NULL AND t.active AND EXISTS (SELECT 1 FROM (VALUES "
        + ", ".join(f"(:c{i}, :k{i}, :n{i}, :s{i}, :b{i})" for i in range(len(SEED)))
        + ") AS s(c, k, n, sub, b) WHERE s.c = t.channel AND s.k = t.kind AND s.n = t.name AND s.sub IS NOT DISTINCT FROM t.subject AND s.b = t.body)"
    ).bindparams(*(sa.bindparam(f"s{i}", type_=sa.String) for i in range(len(SEED))))
    params = {f"{p}{i}": v for i, row in enumerate(SEED) for p, v in zip("cknsb", row, strict=True)}
    if bind.execute(seeded, params).scalar() != bind.execute(sa.text("SELECT count(*) FROM tel_message_templates")).scalar():
        return True
    other_scripts = bind.execute(
        sa.text("SELECT count(*) FROM tel_scripts WHERE NOT (active AND name = :n AND steps::jsonb = CAST(:steps AS jsonb))"),
        {"n": SCRIPT_NAME, "steps": json.dumps(SCRIPT_STEPS)},
    ).scalar()
    return bool(other_scripts)


def downgrade() -> None:
    if not op.get_context().as_sql and _manager_data(op.get_bind()):
        raise RuntimeError("Cannot downgrade 0078_tel_content: manager data exists (assets, or edited templates/scripts). Remove it deliberately first.")
    op.drop_table("tel_message_templates")
    op.drop_table("tel_assets")
    op.drop_table("tel_scripts")
