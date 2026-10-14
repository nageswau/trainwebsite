"""dtu-001 §4.4: the idempotent Direct Tie-ups loader. Creates what is missing, fills only empty fields, never overwrites a stored value.

    python -m app.direct_tieups.load [--dry-run] [--file seed/direct_tieups.json]
"""

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.main  # noqa: F401  (loads the routers first: the services import each other in a cycle that only resolves in that order)
from app.models import AuditLog, Country, OverseasCourse, Scholarship, University
from app.schemas import AgentCommissionIn, CourseIn, UniversityCreate
from app.seed import catalogue_country
from app.services.partnership_universities import free_slug, name_key_of, next_code
from app.services.university_courses import check_rules, derive_texts, title_key

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "seed" / "direct_tieups.json"
FILL_FIELDS = ("logo_url", "campuses", "fee_structure", "website", "overview", "deadlines", "scholarships")
COUNT_KEYS = ("universities_created", "universities_updated", "courses_created", "courses_skipped", "scholarships_created", "conflicts", "countries_published", "country_needs_content", "universities_internal")
UNI_KEYS = ("city", "institution_type", "website", "overview", "campuses", "fee_structure", "logo_url")
COURSE_KEYS = ("title", "level", "category", "duration", "tuition_amount", "tuition_currency", "intakes", "campus", "fee_text", "intake_text")
COUNTRIES_FILE = Path(__file__).resolve().parents[2] / "seed" / "countries.json"


def _empty(value) -> bool:
    return value is None or value == "" or value == []


def _commission(entry: dict | None) -> dict:
    entry = entry or {}
    percent, amount = entry.get("percent"), entry.get("amount")
    return {
        "agent_commission_percent": Decimal(percent) if percent not in (None, "") else None,
        "agent_commission_amount": Decimal(amount) if amount not in (None, "") else None,
        "agent_commission_currency": entry.get("currency") if amount not in (None, "") else None,
        "agent_commission_note": entry.get("note"),
    }


async def _scholarship_ids(db: AsyncSession, uni: University, country: Country, texts: list[str], cache: dict, counts: dict) -> list[str]:
    ids = []
    for raw in texts:
        text = raw[:200]  # the title column length: look up by exactly what is inserted
        key = text.lower()
        if key not in cache:
            row = await db.scalar(
                select(Scholarship).where(Scholarship.university_id == uni.id, func.lower(Scholarship.title) == key).order_by(Scholarship.created_at)
            )
            if row is None:
                row = Scholarship(title=text, university_id=uni.id, country_id=country.id, eligibility="See university", amount=text[:120], active=True)
                db.add(row)
                await db.flush()
                counts["scholarships_created"] += 1
            cache[key] = str(row.id)
        ids.append(cache[key])
    return ids


async def _course_keys(db: AsyncSession, uni: University) -> set[tuple[str, str]]:
    rows = (await db.execute(select(OverseasCourse.title, OverseasCourse.level).where(OverseasCourse.university_id == uni.id))).all()
    return {title_key(title, level) for title, level in rows}


def _commission_tuple(values: dict) -> tuple:
    return values["agent_commission_percent"], values["agent_commission_amount"], values["agent_commission_currency"]


def _reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return str(exc.detail) if isinstance(exc, HTTPException) else str(exc)


def _validate(data: list[dict], countries: dict) -> list[dict]:
    """Every university and course goes through the manual-add schemas and rules before anything is written; one bad row fails the run. Returns each entry with the
    validated (normalised) values in place of the raw ones."""
    checked: list[dict] = []
    for entry in data:
        out = dict(entry)
        try:
            uni = UniversityCreate.model_validate(
                {
                    "name": entry["name"],
                    "country_id": countries[entry["country_iso2"]].id,
                    "city": entry.get("city") or "",
                    "institution_type": entry.get("institution_type") or "university",
                    "website": entry.get("website"),
                    "overview": entry.get("overview") or "",
                    "campuses": entry.get("campuses") or None,
                    "fee_structure": entry.get("fee_structure"),
                    "logo_url": entry.get("logo_url"),
                }
            ).model_dump()
            out.update({k: uni[k] for k in UNI_KEYS})
        except Exception as exc:
            raise ValueError(f"{entry['name']}: invalid university: {_reason(exc)}") from exc
        raw_commission = entry.get("agent_commission")
        if raw_commission:
            try:
                out["agent_commission"] = AgentCommissionIn.model_validate(raw_commission).model_dump()
            except Exception as exc:
                raise ValueError(f"{entry['name']}: invalid agent_commission: {_reason(exc)}") from exc
        out["courses"] = []
        for item in entry.get("courses", []):
            try:
                body = CourseIn.model_validate(
                    {
                        "title": item["title"],
                        "level": item["level"],
                        "category": item["category"],
                        "duration": item["duration"],
                        "tuition_amount": item.get("tuition_amount") or None,
                        "tuition_currency": item.get("tuition_currency") if item.get("tuition_amount") else None,
                        "intakes": item.get("intakes") or [],
                        "campus": item.get("campus"),
                        "fee_text": item.get("fee_text"),
                        "intake_text": item.get("intake_text"),
                    }
                )
                dumped = body.model_dump()
                check_rules(dumped)
                out["courses"].append({**item, **{k: dumped[k] for k in COURSE_KEYS}})
            except Exception as exc:
                raise ValueError(f"{entry['name']} / {item.get('title')}: invalid course: {_reason(exc)}") from exc
        checked.append(out)
    return checked


async def _publish_countries(db: AsyncSession, data: list[dict], countries: dict, counts: dict, notes: list[str]) -> None:
    """DT18: a hidden destination country with a seed/countries.json row is published through the seed's own function; one without
    stays hidden and is reported."""
    rows = {row[5]: row for row in json.loads(COUNTRIES_FILE.read_text(encoding="utf-8"))}
    done: set[str] = set()
    for code, country in sorted(countries.items()):
        if country.catalogue_visible:
            continue
        row = rows.get(code)
        if (country.overview or "").strip():
            country.catalogue_visible = True  # R13: it already has its content; only the flag changes
        elif row is not None and row[0] == country.slug:
            await catalogue_country(db, row, {})
        if country.catalogue_visible:
            counts["countries_published"] += 1
            db.add(
                AuditLog(user_id=None, action="country.direct_tieup_publish", entity_type="country", entity_id=str(country.id), metadata_json={"iso2": code})
            )
        elif code not in done:
            done.add(code)
            counts["country_needs_content"] += 1
            for entry in data:
                if entry["country_iso2"] == code:
                    notes.append(f"{code}: {entry['name']} stays hidden until {country.name} has catalogue content")
    await db.flush()


async def load(db: AsyncSession, data: list[dict], commit: bool = True) -> dict[str, int]:
    counts = dict.fromkeys(COUNT_KEYS, 0)
    codes = {entry["country_iso2"] for entry in data}
    countries = {c.iso2: c for c in (await db.scalars(select(Country).where(Country.iso2.in_(codes)))).all()}
    for code in sorted(codes):
        if code not in countries:
            raise ValueError(f"unknown country {code}")
    data = _validate(data, countries)
    hidden: list[str] = []
    internal: list[str] = []
    try:
        await _publish_countries(db, data, countries, counts, hidden)
        for entry in data:
            country = countries[entry["country_iso2"]]
            matches = (
                await db.scalars(
                    select(University)
                    .where(University.country_id == country.id, University.name_key == name_key_of(entry["name"]))
                    .order_by(University.created_at, University.id)
                )
            ).all()
            if len(matches) > 1:
                counts["conflicts"] += 1  # several rows for one name: the oldest is used
            commission = _commission(entry.get("agent_commission"))
            has_commission = commission["agent_commission_percent"] is not None or commission["agent_commission_amount"] is not None
            fields: list[str] = []
            if matches:
                uni, created = matches[0], False
                for field in FILL_FIELDS:
                    if _empty(getattr(uni, field)) and not _empty(entry.get(field)):
                        setattr(uni, field, entry[field])
                        fields.append(field)
                if uni.agent_commission_percent is None and uni.agent_commission_amount is None:
                    if has_commission:
                        for key, value in commission.items():
                            if key == "agent_commission_note" and not _empty(uni.agent_commission_note):
                                continue  # a stored note is never overwritten
                            setattr(uni, key, value)
                        fields.append("agent_commission")
                elif has_commission and _commission_tuple(commission) != (
                    uni.agent_commission_percent,
                    uni.agent_commission_amount,
                    uni.agent_commission_currency,
                ):
                    counts["conflicts"] += 1  # reported, never changed
                if fields:
                    counts["universities_updated"] += 1
            else:
                code = await next_code(db)
                uni, created = (
                    University(
                        university_code=code,
                        slug=await free_slug(db, entry["name"], code),
                        country_id=country.id,
                        name=entry["name"],
                        city=entry.get("city") or "",
                        institution_type=entry.get("institution_type") or "university",
                        catalogue_visible=country.catalogue_visible,  # R15: internal while its country stays hidden
                        active=True,
                        requirements=[],
                        eligibility="",
                        overview=entry.get("overview") or "",
                        deadlines=entry.get("deadlines") or [],
                        scholarships=entry.get("scholarships") or [],
                        website=entry.get("website"),
                        logo_url=entry.get("logo_url"),
                        campuses=entry.get("campuses") or [],
                        fee_structure=entry.get("fee_structure"),
                        **commission,
                    ),
                    True,
                )
                db.add(uni)
                await db.flush()
                counts["universities_created"] += 1
                if not country.catalogue_visible:
                    counts["universities_internal"] += 1
                    internal.append(f"{country.iso2}: {entry['name']} created internal (not public)")
                fields = [f for f in FILL_FIELDS if not _empty(entry.get(f))] + (["agent_commission"] if has_commission else [])

            cache: dict[str, str] = {}
            await _scholarship_ids(db, uni, country, entry.get("scholarships") or [], cache, counts)
            keys = await _course_keys(db, uni)
            made = 0
            for item in entry.get("courses", []):
                key = title_key(item["title"], item["level"])
                if key in keys:
                    counts["courses_skipped"] += 1
                    continue
                amount = Decimal(item["tuition_amount"]) if item.get("tuition_amount") not in (None, "") else None
                course = OverseasCourse(
                    university_id=uni.id,
                    title=item["title"],
                    level=item["level"],
                    category=item["category"],
                    duration=item["duration"],
                    tuition_fee="",
                    intake="",
                    tuition_amount=amount,
                    tuition_currency=item.get("tuition_currency") if amount is not None else None,
                    intakes=item.get("intakes") or [],
                    campus=item.get("campus"),
                    fee_text=item.get("fee_text"),
                    intake_text=item.get("intake_text"),
                    scholarship_ids=await _scholarship_ids(db, uni, country, item.get("scholarships") or [], cache, counts),
                    active=True,
                )
                derive_texts(course, {"tuition_amount", "tuition_currency", "intakes"})
                db.add(course)
                keys.add(key)
                made += 1
                counts["courses_created"] += 1
            if created or fields or made:
                db.add(
                    AuditLog(
                        user_id=None,
                        action="university.direct_tieup_load",
                        entity_type="university",
                        entity_id=str(uni.id),
                        metadata_json={"created": created, "fields": fields, "courses_created": made},
                    )
                )
            await db.flush()
    except BaseException:
        await db.rollback()
        raise
    for line in hidden + internal:
        print(line)
    if commit:
        await db.commit()
    else:
        await db.rollback()
    return counts


async def main() -> None:
    from app.core.database import SessionLocal, engine

    parser = argparse.ArgumentParser(description="Load the Direct Tie-ups catalogue (never overwrites stored values).")
    parser.add_argument("--dry-run", action="store_true", help="run everything, then roll back")
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    args = parser.parse_args()
    path = Path(args.file)
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parents[2] / path
    data = json.loads(path.read_text(encoding="utf-8"))
    async with SessionLocal() as db:
        counts = await load(db, data, commit=not args.dry_run)
    await engine.dispose()
    print(json.dumps({"dry_run": args.dry_run, **counts}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
