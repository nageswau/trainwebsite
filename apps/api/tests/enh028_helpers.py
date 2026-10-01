"""Shared builders for the ENH-028 bulk data-entry tests (docs/superpowers/plans/2026-10-01-enh-028-bulk-data-entry.md).

Each test builds its own throwaway schools (ENH-005's `mk_school`), so runs never collide with each other or the seeded data."""

import csv
import io
import uuid

from sqlalchemy import select

from app.models import SchoolBulkUploadBatch
from tests.enh005_helpers import login, mk_school, mk_staff

BASE = "/api/v1/school"
RESULTS_URL = f"{BASE}/academic-team/results/bulk-upload"
PSYCH_URL = f"{BASE}/psychometric-team/records/bulk-upload"
TEST_PREP_URL = f"{BASE}/academic-team/test-prep-records/bulk-upload"
LANGUAGE_URL = f"{BASE}/academic-team/language-records/bulk-upload"

RESULT_HEADER = ["student_code", "student_name", "school_name", "academic_year", "term", "subject", "max_marks", "marks_obtained", "grade", "teacher_remarks"]


def csv_bytes(header: list[str], rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(name, "") for name in header])
    return buffer.getvalue().encode("utf-8")


def result_row(student, subject: str = "Mathematics", max_marks: str = "100", obtained: str = "80", **over) -> dict:
    return {"student_code": student.student_code, "student_name": student.full_name, "academic_year": "2026", "term": "Term 1", "subject": subject, "max_marks": max_marks, "marks_obtained": obtained, **over}


async def upload(client, url: str, data: bytes, key: str | None = None):
    return await client.post(url, files={"file": ("bulk.csv", data, "text/csv")}, headers={"Idempotency-Key": key or uuid.uuid4().hex})


async def world(db, *, role: str = "academic_team", students: int = 3, tier: str | None = "platinum") -> dict:
    """A school in the member's portfolio (its first student has a linked parent) plus a second school that is NOT in it."""
    w = await mk_school(db, label="Mine", students=students, tier=tier)
    other = await mk_school(db, admin=w["admin"], label="Other", students=1)
    member = await mk_staff(db, w["school"], w["admin"], role)
    return {**w, "member": member, "outsider": other["students"][0]}


async def batches_of(db, user) -> list[SchoolBulkUploadBatch]:
    return list((await db.scalars(select(SchoolBulkUploadBatch).where(SchoolBulkUploadBatch.uploaded_by_user_id == user.id))).all())


__all__ = ["login", "mk_school", "mk_staff"]
