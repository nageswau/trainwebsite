"""upc-005 (DEC-SCOPE-128, spec §1): the University CSV import's rows -- parse, check for duplicates, create, report.

Functions only; nothing here commits -- the route owns the transaction. Every row goes through `UniversityCreate`, so an import accepts
exactly what a manual create accepts (IM2). The work is set-based (spec §3): one query each for the countries, the key locks, the existing
matches, the codes and the taken slugs, then one flush."""

import csv
import io
import re
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_bulk import _safe_cell
from app.core.identifiers import normalize_key
from app.models import (
    COURSE_LEVELS,
    INSTITUTION_TYPES,
    PARTNERSHIP_POTENTIALS,
    UNIVERSITY_OWNERSHIP_TYPES,
    UNIVERSITY_PRIORITIES,
    UNIVERSITY_RELATIONSHIPS,
    Country,
    University,
    UniversityImportBatch,
    User,
)
from app.schemas import UniversityCreate, validation_message
from app.services import partnership_universities as svc

COLUMNS = (
    "name",
    "country",
    "city",
    "institution_type",
    "ownership_type",
    "state_region",
    "website",
    "course_levels",
    "popular_programs",
    "international_office",
    "existing_relationship",
    "priority",
    "partnership_potential",
    "overview",
)
REQUIRED = ("name", "country", "city", "institution_type")
MAX_ROWS = 5000
TEXT_LIMIT = 200  # how much of the given name / country the report keeps
LIST_FIELDS = ("course_levels", "popular_programs")
# IM2: a value list accepts its code or its label in any case ("Language School" = "language_school", "a" = "A", "phd" = "PhD").
CHOICES = {
    "institution_type": INSTITUTION_TYPES,
    "ownership_type": UNIVERSITY_OWNERSHIP_TYPES,
    "existing_relationship": UNIVERSITY_RELATIONSHIPS,
    "priority": UNIVERSITY_PRIORITIES,
    "partnership_potential": PARTNERSHIP_POTENTIALS,
    "course_levels": COURSE_LEVELS,
}
REPORT_COLUMNS = ("row_number", "status", "name", "country", "university_code", "reason")


def _fold(value: str) -> str:
    return re.sub(r"[\s_-]+", "_", normalize_key(value, 80))


_CANONICAL = {field: {_fold(v): v for v in values} for field, values in CHOICES.items()}


def _choice(field: str, value: str) -> str:
    """The stored value for a code or a label; anything else (and every free-text field) passes through unchanged, for UniversityCreate
    to validate with its own message."""
    return _CANONICAL[field].get(_fold(value), value) if field in _CANONICAL else value


def country_index(countries: list[Country]) -> dict[str, Country]:
    """IM3: an ISO-2 code or a country name, compared after NFKC + casefold."""
    index = {normalize_key(c.name, TEXT_LIMIT): c for c in countries}
    index.update({c.iso2.casefold(): c for c in countries if c.iso2})
    return index


def parse_row(cells: dict[str, str], countries: dict[str, Country]) -> UniversityCreate | str:
    """The validated create payload, or the reason the row is invalid."""
    given = cells.get("country", "")
    if not given:
        return "country is required"
    country = countries.get(normalize_key(given, TEXT_LIMIT))
    if country is None:
        return f"Unknown country: {given[:80]}"
    values: dict = {"country_id": country.id}
    for field, value in cells.items():
        if field == "country" or not value:
            continue
        if field in LIST_FIELDS:
            values[field] = [_choice(field, part.strip()) for part in value.split(";") if part.strip()]
        else:
            values[field] = _choice(field, value)
    try:
        return UniversityCreate.model_validate(values)
    except ValidationError as exc:
        return validation_message(exc)


def _result(line: int, cells: dict[str, str]) -> dict:
    return {
        "row_number": line,
        "status": "invalid",
        "name": cells.get("name", "")[:TEXT_LIMIT],
        "country": cells.get("country", "")[:TEXT_LIMIT],
        "university_id": None,
        "university_code": None,
        "matches": [],
        "reason": None,
    }


async def _existing(db: AsyncSession, keys: set[tuple[UUID, str]]) -> dict[tuple[UUID, str], list[str]]:
    """IM5: the master's codes per (country, name key), inactive rows included, ordered by code."""
    names = {name_key for _, name_key in keys}
    stmt = select(University.country_id, University.name_key, University.university_code).where(University.name_key.in_(names)).order_by(University.university_code)
    found: dict[tuple[UUID, str], list[str]] = {}
    for country_id, name_key, code in (await db.execute(stmt)).all():
        if (country_id, name_key) in keys:
            found.setdefault((country_id, name_key), []).append(code)
    return found


async def _codes(db: AsyncSession, count: int) -> list[str]:
    values = (await db.scalars(text("SELECT nextval('university_code_seq') FROM generate_series(1, :n)"), {"n": count})).all()
    return [f"UNV-{v:06d}" for v in values]


async def _slugs(db: AsyncSession, names: list[str], codes: list[str]) -> list[str]:
    """upc-003 UM14 for every row at once: the name's slug, or name + code when the slug is taken (in the master or earlier in the file)."""
    bases = [svc.slug_base(name) for name in names]
    taken = set((await db.scalars(select(University.slug).where(University.slug.in_(set(bases))))).all())
    slugs = []
    for base, code in zip(bases, codes, strict=True):
        slugs.append(f"{base}-{code.lower()}" if base in taken else base)
        taken.add(base)
    return slugs


async def run(db: AsyncSession, user: User, batch: UniversityImportBatch, filled: list[tuple[int, dict[str, str]]]) -> list[dict]:
    """Each row's outcome, in file order. Created rows are unowned, internal and active (IM4), each audited (IM11)."""
    countries = country_index(list((await db.scalars(select(Country))).all()))
    results: list[dict] = []
    first_row: dict[tuple[UUID, str], int] = {}
    candidates: list[tuple[dict, UniversityCreate, tuple[UUID, str]]] = []
    for line, cells in filled:
        result = _result(line, cells)
        results.append(result)
        parsed = parse_row(cells, countries)
        if isinstance(parsed, str):
            result["reason"] = parsed
            continue
        key = (parsed.country_id, svc.name_key_of(parsed.name))
        if key in first_row:
            result.update(status="duplicate", reason=f"Repeats row {first_row[key]} of this file")
            continue
        first_row[key] = line
        candidates.append((result, parsed, key))
    if not candidates:
        return results
    # IM9: hold every key's lock (upc-004 UD4), so a manual create of the same name + country waits for this import, then look.
    lock_keys = sorted(svc.duplicate_lock_key(country_id, name_key) for country_id, name_key in first_row)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(k, 0)) FROM unnest(CAST(:keys AS text[])) AS k"), {"keys": lock_keys})
    existing = await _existing(db, set(first_row))
    new = []
    for result, parsed, key in candidates:
        codes = existing.get(key)
        if codes:
            result.update(status="duplicate", matches=codes[: svc.MAX_MATCHES], reason=f"Already in the University Master: {', '.join(codes[:3])}")
        else:
            new.append((result, parsed))
    if not new:
        return results
    codes = await _codes(db, len(new))
    slugs = await _slugs(db, [parsed.name for _, parsed in new], codes)
    for (result, parsed), code, slug in zip(new, codes, slugs, strict=True):
        uni = University(
            id=uuid4(),
            university_code=code,
            slug=slug,
            catalogue_visible=False,
            requirements=[],
            deadlines=[],
            scholarships=[],
            **parsed.model_dump(exclude={"rankings", "duplicate_reason"}),
        )
        db.add(uni)
        svc.audit(db, user, "create", uni.id, {"code": code, "import_batch_id": str(batch.id)})
        result.update(status="created", university_id=str(uni.id), university_code=code)
    await db.flush()
    return results


def summary(batch: UniversityImportBatch, uploader: User) -> dict:
    """A history row; the report adds `rows`."""
    return {
        "id": batch.id,
        "uploaded_by": {"id": uploader.id, "full_name": uploader.full_name},
        **{k: getattr(batch, k) for k in ("total_rows", "created_count", "duplicate_count", "invalid_count", "created_at")},
    }


def report_csv(batch: UniversityImportBatch) -> str:
    """IM10: the per-row report for a spreadsheet; every text cell is formula-escaped (it echoes what the file said)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_COLUMNS)
    for row in batch.results_json:
        writer.writerow([row["row_number"], row["status"], *(_safe_cell(row[c] or "") for c in ("name", "country", "university_code", "reason"))])
    return buffer.getvalue()
