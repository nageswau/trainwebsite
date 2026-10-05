"""Shared builders for ENH-029 bulk school onboarding tests (docs/superpowers/plans/2026-10-01-enh-029-bulk-school-onboarding.md)."""

import csv
import io
import uuid

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"
UPLOAD_URL = "/api/v1/overseas-admin/schools/bulk-upload"
TEMPLATE_URL = "/api/v1/overseas-admin/schools/bulk-template"
HEADER = ["name", "city", "coordinator_full_name", "coordinator_email", "tier"]


async def mk_admin(db, role: str = "overseas_admin") -> User:
    user = User(
        email=f"enh029-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name=f"ENH-029 {role}",
        role=role,
        division="overseas",
        active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": user.division})
    assert response.status_code == 200, response.text


def school_row(tag: str | None = None, **over) -> dict:
    tag = tag or uuid.uuid4().hex[:8]
    return {"name": f"ENH029 School {tag}", "city": "Pune", "coordinator_full_name": f"Coord {tag}", "coordinator_email": f"enh029-coord-{tag}@example.local", **over}


def csv_bytes(rows: list[dict], header: list[str] | None = None) -> bytes:
    header = header or HEADER
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(name, "") for name in header])
    return buffer.getvalue().encode("utf-8")


async def upload(client, data: bytes, key: str | None = None):
    return await client.post(UPLOAD_URL, files={"file": ("schools.csv", data, "text/csv")}, headers={"Idempotency-Key": key or uuid.uuid4().hex})
