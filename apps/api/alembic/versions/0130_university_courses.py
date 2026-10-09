"""upc-017 -- overseas_courses becomes the §16 course master; course_import_batches (CSV import).

Revision ID: 0130_university_courses
Revises: 0129_university_commission_terms

docs/superpowers/specs/2026-10-09-upc-017-course-master-design.md §2 (DEC-SCOPE-145). New nullable / defaulted columns, so every existing
course, application, shortlist entry and commission term keeps its row and its course_id. 0001 builds a fresh database from the current
models, which already carry them, so each step runs only when missing (0117's idiom).

CO5 (Q-21): the legacy `tuition_fee` / `intake` texts are parsed best effort into the structured columns where those are still empty; the
texts themselves are never changed. CURRENCIES / MONTHS / TESTS / CHECKS repeat app.models (test_upc_017_migration). downgrade() refuses
while any course holds data only the master columns carry (the parsed tuition and intakes are re-derivable from the kept texts) or any
import batch exists.
"""

import re
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0130_university_courses"
down_revision = "0129_university_commission_terms"
branch_labels = None
depends_on = None

COURSES = "overseas_courses"
BATCHES = "course_import_batches"
UUID = postgresql.UUID(as_uuid=True)
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TESTS = ("IELTS", "TOEFL", "PTE", "Duolingo", "Other")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.COURSE_CHECKS
    "ck_overseas_courses_tuition": "(tuition_amount IS NULL) = (tuition_currency IS NULL) AND (tuition_amount IS NULL OR tuition_amount >= 0)",
    "ck_overseas_courses_tuition_currency": _one_of("tuition_currency", CURRENCIES),
    "ck_overseas_courses_fee": "(application_fee IS NULL) = (application_fee_currency IS NULL) AND (application_fee IS NULL OR application_fee >= 0)",
    "ck_overseas_courses_fee_currency": _one_of("application_fee_currency", CURRENCIES),
    "ck_overseas_courses_english_test": _one_of("english_test", TESTS),
    "ck_overseas_courses_english_score": "english_score IS NULL OR (english_score > 0 AND english_test IS NOT NULL)",
    "ck_overseas_courses_commission": "commission_percent IS NULL OR commission_amount IS NULL",
    "ck_overseas_courses_commission_percent": "commission_percent IS NULL OR (commission_percent > 0 AND commission_percent <= 100)",
    "ck_overseas_courses_commission_amount": "(commission_amount IS NULL) = (commission_currency IS NULL) AND (commission_amount IS NULL OR commission_amount > 0)",
    "ck_overseas_courses_commission_currency": _one_of("commission_currency", CURRENCIES),
}


def _columns() -> tuple[sa.Column, ...]:
    """Fresh Column objects per call: a Column can be attached to one table only."""
    return (
        sa.Column("tuition_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("tuition_currency", sa.String(3), nullable=True),
        sa.Column("application_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("application_fee_currency", sa.String(3), nullable=True),
        sa.Column("intakes", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("entry_requirements", sa.Text(), nullable=True),
        sa.Column("english_test", sa.String(10), nullable=True),
        sa.Column("english_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("scholarship_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("application_process", sa.Text(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("commission_currency", sa.String(3), nullable=True),
    )


INDEX = "ix_overseas_courses_university_level"
# Columns a downgrade would lose for good (tuition and intakes live on in the legacy texts).
MASTER_ONLY = (
    "application_fee IS NOT NULL OR entry_requirements IS NOT NULL OR english_test IS NOT NULL OR scholarship_ids::text <> '[]' "
    "OR application_process IS NOT NULL OR deadline IS NOT NULL OR NOT active OR commission_percent IS NOT NULL OR commission_amount IS NOT NULL"
)

# CO5: a currency word or symbol, then (or after) one number; a bare "$" is ambiguous and stays unparsed.
_SYMBOLS = {"£": "GBP", "€": "EUR", "₹": "INR", "US$": "USD", "RS": "INR", "RS.": "INR"}
_MONEY = re.compile(r"^(?:(?P<pre>US\$|[£€₹]|[A-Za-z]{2,3}\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d{1,2})?)(?:\s*(?P<post>[A-Za-z]{3}))?$")
_MONTH_WORDS = {m.lower(): m for m in MONTHS} | {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr", "june": "Jun", "july": "Jul", "august": "Aug", "sept": "Sep",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}  # fmt: skip


def _currency(word: str | None) -> str | None:
    if word is None:
        return None
    upper = word.upper()
    return upper if upper in CURRENCIES else _SYMBOLS.get(word) or _SYMBOLS.get(upper)


def parse_tuition(text: str) -> tuple[Decimal, str] | None:
    """The amount and currency of a legacy fee text such as "£31,000" or "CAD 42,000"; None when it is not exactly one priced amount."""
    match = _MONEY.match((text or "").strip())
    if not match or (match["pre"] and match["post"]):
        return None
    currency = _currency(match["pre"] or match["post"])
    if currency is None:
        return None
    try:
        return Decimal(match["num"].replace(",", "")), currency
    except InvalidOperation:  # pragma: no cover - the pattern only admits digits
        return None


def parse_intakes(text: str) -> list[str]:
    """The months named by a legacy intake text ("February/July" → [Feb, Jul]) in calendar order; [] when any word is not a month."""
    words = [w for w in re.split(r"[\s,/;&]+|\band\b", (text or "").strip().lower()) if w]
    months = [_MONTH_WORDS.get(w) for w in words]
    if not months or None in months:
        return []
    return [m for m in MONTHS if m in months]


def _parse_legacy_rows(bind) -> None:
    """CO5: fill only what is still empty; the legacy texts stay as they are."""
    table = sa.table(COURSES, sa.column("id"), sa.column("tuition_amount"), sa.column("tuition_currency"), sa.column("intakes", sa.JSON))
    rows = bind.execute(sa.text(f"SELECT id, tuition_fee, intake, tuition_amount IS NULL, intakes::text = '[]' FROM {COURSES} WHERE tuition_amount IS NULL OR intakes::text = '[]'")).all()
    for course_id, fee, intake, no_amount, no_months in rows:
        values = {}
        if no_amount and (tuition := parse_tuition(fee)) is not None:
            values["tuition_amount"], values["tuition_currency"] = tuition
        if no_months and (months := parse_intakes(intake)):
            values["intakes"] = months
        if values:
            bind.execute(sa.update(table).where(table.c.id == course_id).values(**values))


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(COURSES)}
    for column in _columns():
        if column.name not in existing:
            op.add_column(COURSES, column)
    constraints = set() if offline else {c["name"] for c in inspector.get_check_constraints(COURSES)}
    for name, sql in CHECKS.items():
        if name not in constraints:
            op.create_check_constraint(name, COURSES, sql)
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes(COURSES)}:
        op.create_index(INDEX, COURSES, ["university_id", "level"])
    if offline or BATCHES not in inspector.get_table_names():
        op.create_table(
            BATCHES,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("file_sha256", sa.String(64), nullable=False),
            *(sa.Column(c, sa.Integer(), server_default=sa.text("0"), nullable=False) for c in ("total_rows", "created_count", "duplicate_count", "invalid_count")),
            sa.Column("results_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_course_import_batches_key"),
            sa.CheckConstraint("created_count + duplicate_count + invalid_count = total_rows", name="ck_course_import_batches_counts"),
        )
        op.create_index("ix_course_import_batches_university", BATCHES, ["university_id", "created_at"])
    if not offline:
        _parse_legacy_rows(op.get_bind())


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {BATCHES} LIMIT 1")).first() or bind.execute(sa.text(f"SELECT 1 FROM {COURSES} WHERE {MASTER_ONLY} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0130_university_courses: course master data exists. Export and remove it deliberately first.")
    op.drop_table(BATCHES)
    op.drop_index(INDEX, table_name=COURSES)
    for name in CHECKS:
        op.drop_constraint(name, COURSES, type_="check")
    for column in _columns():
        op.drop_column(COURSES, column.name)
