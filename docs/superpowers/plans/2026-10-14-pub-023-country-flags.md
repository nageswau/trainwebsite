# PUB-023 Country Flags (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each country's flag (a bundled SVG chosen by the stored ISO code) next to the country name on the phase-1 public, agent and admin screens.

**Architecture:**
- The flag-icons 4:3 SVGs are copied into `apps/web/public/flags/`.
- One server-safe `CountryFlag` component renders `<img src="/flags/xx.svg">`. A pure `flagSrc()` helper accepts only a two-letter code.
- Three read-only API fields deliver the code where the web doesn't have it yet: `CountryOut.iso2`, the course rows' `country_iso2`, and the country lookup's `iso2`.
- A repo script checks that every ISO code from migration 0101 has an SVG.

**Tech Stack:**
- FastAPI + SQLAlchemy async + pytest (`apps/api`).
- Next.js App Router + React + vitest + Testing Library + Playwright (`apps/web`).
- Python 3 (stdlib only) for the repo script.

**Spec:** `docs/superpowers/specs/2026-10-14-pub-023-country-flags-design.md` (including its §3.1 amendment)

## Global Constraints

- Feature ID `PUB-023`; decision `DEC-SCOPE-222`; API contract section `§12EJ`. No migration and no RBAC change.
- Flags come only from `iso2`. The guard is `/^[A-Za-z]{2}$/` after trimming. File name: `/flags/<lower-case code>.svg`.
- Image attributes: `alt=""`, `aria-hidden="true"`, `loading="lazy"`, `decoding="async"`. Sizes: `inline` = 20×15, `large` = 40×30.
- Missing or invalid `iso2` → render nothing. The public country cards keep the existing 🌍 instead.
- No third-party requests. No new npm dependency in `package.json`. flag-icons is only a source to copy files from.
- Public endpoints stay unauthenticated. `/lookups/countries` keeps its existing role check.
- Every screen only gains a flag; its text, order and layout are otherwise unchanged.
- Never change product behaviour to make a draft test pass. The three pinned-shape tests named in Task 3 are updated on purpose (DEC-SCOPE-222 changes the contract), and each gains only the new key.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## How to run tests (worktree `../pub-023`, compose project `pub023`)

Run from the worktree root `C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/pub-023` in Git Bash. Always pass `-f docker-compose.yml`, so the Caddy override is never loaded. The mount path must be the Windows form.

```bash
WT="C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/pub-023"
API_TEST() { docker compose -p pub023 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "$WT/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q $*"; }
WEB_TEST() { MSYS_NO_PATHCONV=1 docker compose -p pub023 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -v "$WT/apps/web:/app" -v /app/node_modules web-test sh -c "$*"; }
```

- If `alembic upgrade head` fails on a stale stamp in the isolated test database, run `alembic stamp --purge 0162_school_values`, then `upgrade head`.
- **The owner starts and stops app stacks** (they manage the docker lifecycle). For Task 7's Playwright run, give the owner the `up` command and wait for them to confirm. One-off `run --rm` test containers are fine.

## Review Focus

- **A country row with `iso2 = NULL`** (test and ad-hoc rows) reaches every screen. Expected: the name only, no broken image, and the 🌍 kept on public cards. Pinned in Task 2 (`flagSrc(null)`) and Task 4 (`UniversityView` with `iso2: null`).
- **Lower-case or space-padded codes** (`" gb "`, `"gb"`). Expected: the same `/flags/gb.svg`. Pinned in Task 2.
- **Path-like or over-long input** (`"../x"`, `"GBR"`, `"G1"`). Expected: nothing rendered and no request. Pinned in Task 2.
- **Every other lookup in `SearchableSelect`** (students, schools, managers…) has no `iso2`. Expected: the options render exactly as before, with no empty `img`. Pinned in Task 5.
- **The global dashboard's other `GlobalCounts` tables** (stages, managers) have no `iso2`. Expected: unchanged. Pinned in Task 6.

---

### Task 1: Flag assets and the coverage script

**Files:**
- Create: `scripts/check_flag_assets.py`
- Create: `apps/web/public/flags/*.svg` (copied)
- Create: `apps/web/public/flags/LICENSE`
- Create: `apps/web/public/flags/README.md`

**Interfaces:**
- Consumes: `apps/api/alembic/versions/0101_country_master.py`, specifically the module-level `_BY_REGION = {region: [(code, name), …]}` literal.
- Produces:
  - `/flags/<code>.svg` for every ISO code, with lower-case file names. Task 2 relies on these.
  - `python scripts/check_flag_assets.py`, which exits 0 or 1.

- [ ] **Step 1: Write the coverage script (it is the failing test)**

`scripts/check_flag_assets.py`:
```python
"""PUB-023 (DEC-SCOPE-222): every ISO country code that migration 0101 creates must have /flags/<code>.svg in the web app.

The api-test and web-test containers each see only their own app, so this cross-app check is a repo script.
Run from anywhere:  python scripts/check_flag_assets.py   (exit 0 = complete, 1 = missing flags listed)
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "apps" / "api" / "alembic" / "versions" / "0101_country_master.py"
FLAGS = ROOT / "apps" / "web" / "public" / "flags"


def iso_codes() -> set[str]:
    """The codes in 0101's `_BY_REGION` literal, read with ast (the migration is never imported)."""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_BY_REGION" for t in node.targets):
            regions = ast.literal_eval(node.value)
            return {code for rows in regions.values() for code, _name in rows}
    raise SystemExit(f"_BY_REGION not found in {MIGRATION}")


def main() -> int:
    codes = iso_codes()
    present = {p.stem.upper() for p in FLAGS.glob("*.svg")} if FLAGS.is_dir() else set()
    missing = sorted(codes - present)
    if missing:
        print(f"{len(missing)} of {len(codes)} ISO codes have no flag in {FLAGS}: {', '.join(missing)}")
        return 1
    print(f"All {len(codes)} ISO codes from migration 0101 have a flag SVG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python scripts/check_flag_assets.py`
Expected: exit 1 and `249 of 249 ISO codes have no flag in …/public/flags: AD, AE, …`.

- [ ] **Step 3: Copy the flag set**

Work in a fresh scratch directory, not inside the repo:
```bash
SCRATCH="$(mktemp -d)"; cd "$SCRATCH"
npm view flag-icons version                # record this version for the README
npm pack flag-icons@"$(npm view flag-icons version)"
tar xzf flag-icons-*.tgz
mkdir -p "$WT/apps/web/public/flags"
# two-letter country files only; skip eu and un (not countries)
for f in package/flags/4x3/??.svg; do b=$(basename "$f"); case "$b" in eu.svg|un.svg) continue;; esac; cp "$f" "$WT/apps/web/public/flags/$b"; done
cp package/LICENSE "$WT/apps/web/public/flags/LICENSE"
cd "$WT"; ls apps/web/public/flags/*.svg | wc -l
```
Expected: about 250 files. Sub-national files such as `gb-eng.svg` are not matched by `??.svg`.

- [ ] **Step 4: Write `apps/web/public/flags/README.md`**

Fill in `<version>` with the value printed by `npm view` in Step 3.

```markdown
# Country flags (PUB-023, DEC-SCOPE-222)

4:3 SVG flags copied from [flag-icons](https://github.com/lipis/flag-icons) `<version>` (MIT, see `LICENSE`) on 2026-10-14.
File names are lower-case ISO 3166-1 alpha-2 codes. Only two-letter country files were copied (`eu` and `un` were left out).
Rendered by `components/CountryFlag.tsx`. `scripts/check_flag_assets.py` checks this folder covers every code migration 0101 creates.
To update: repeat the copy from a newer flag-icons release and re-run the script.
```

- [ ] **Step 5: Run the script to confirm it passes**

Run: `python scripts/check_flag_assets.py`
Expected: exit 0 and `All 249 ISO codes from migration 0101 have a flag SVG.`
If a code is listed as missing, stop and report it. Don't invent a file.

Build check (confirmed while planning): `apps/web/Dockerfile` copies `/app/public` into the image (`COPY --from=builder /app/public ./public`), and `Dockerfile.dockerignore` excludes only tests and configs, so `public/flags` ships with no Docker change.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_flag_assets.py apps/web/public/flags
git commit -m "feat(pub-023): bundle flag-icons country SVGs and the ISO coverage check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `flagSrc` helper and the `CountryFlag` component

**Files:**
- Create: `apps/web/lib/countryFlag.ts`
- Create: `apps/web/components/CountryFlag.tsx`
- Modify: `apps/web/app/globals.css` (append rules at the end)
- Test: `apps/web/tests/lib/countryFlag.test.ts`, `apps/web/tests/components/CountryFlag.test.tsx`

**Interfaces:**
- Consumes: `/flags/<code>.svg` (Task 1).
- Produces:
  - `flagSrc(iso2: string | null | undefined): string | null`, exported from `@/lib/countryFlag`;
  - `export type FlagSize = "inline" | "large"`;
  - `export default function CountryFlag({ iso2, size = "inline" }: { iso2: string | null | undefined; size?: FlagSize })` from `@/components/CountryFlag`, which returns `null` when `flagSrc` returns `null`.

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/lib/countryFlag.test.ts`:
```ts
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { flagSrc } from "@/lib/countryFlag";

describe("flagSrc", () => {
  it("maps a two-letter code to the lower-case SVG path", () => {
    expect(flagSrc("GB")).toBe("/flags/gb.svg");
    expect(flagSrc("gb")).toBe("/flags/gb.svg");
    expect(flagSrc(" ae ")).toBe("/flags/ae.svg");
  });
  it.each([null, undefined, "", "  ", "G", "G1", "GBR", "../x", "g/"])("returns null for %j", (value) => {
    expect(flagSrc(value as string | null | undefined)).toBeNull();
  });
});

describe("public/flags", () => {
  const files = readdirSync(join(process.cwd(), "public", "flags")).filter((f) => f.endsWith(".svg"));
  it("holds only two-letter lower-case SVGs", () => {
    expect(files.length).toBeGreaterThan(240);
    for (const f of files) expect(f).toMatch(/^[a-z]{2}\.svg$/);
  });
  it("has the six published destinations", () => {
    for (const code of ["gb", "au", "us", "ae", "fr", "de"]) expect(files).toContain(`${code}.svg`);
  });
});
```

`apps/web/tests/components/CountryFlag.test.tsx`:
```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CountryFlag from "@/components/CountryFlag";

afterEach(cleanup);
describe("CountryFlag", () => {
  it("renders a decorative inline flag by default", () => {
    const { container } = render(<CountryFlag iso2="GB" />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/flags/gb.svg");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["20", "15"]);
    expect(img.className).toBe("country-flag country-flag--inline");
  });
  it("renders the large size", () => {
    const img = render(<CountryFlag iso2="au" size="large" />).container.querySelector("img")!;
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["40", "30"]);
  });
  it.each([null, undefined, "", "G1", "GBR", "../x"])("renders nothing for %j", (value) => {
    const { container } = render(<CountryFlag iso2={value as string | null | undefined} />);
    expect(container.innerHTML).toBe("");
  });
});
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `WEB_TEST "npx vitest run tests/lib/countryFlag.test.ts tests/components/CountryFlag.test.tsx"`
Expected: FAIL. The modules `@/lib/countryFlag` and `@/components/CountryFlag` don't exist yet. (The `public/flags` cases already pass after Task 1.)

- [ ] **Step 3: Implement**

`apps/web/lib/countryFlag.ts`:
```ts
// PUB-023 (DEC-SCOPE-222): a country's flag is the bundled /flags/<iso2>.svg. Only a two-letter code is ever turned into a path,
// so nothing else (empty, three letters, "../x") can reach the URL; null means "show no flag" (F3).
const CODE = /^[A-Za-z]{2}$/;

export function flagSrc(iso2: string | null | undefined): string | null {
  const code = (iso2 ?? "").trim();
  return CODE.test(code) ? `/flags/${code.toLowerCase()}.svg` : null;
}
```

`apps/web/components/CountryFlag.tsx`:
```tsx
import { flagSrc } from "@/lib/countryFlag";

// PUB-023 (DEC-SCOPE-222): a decorative flag before a country name (F4: the name is always beside it, so alt="" + aria-hidden).
// Server-safe (no state or effects) so public pages stay server-rendered; renders nothing without a valid code (F3).
const SIZES = { inline: [20, 15], large: [40, 30] } as const;
export type FlagSize = keyof typeof SIZES;

export default function CountryFlag({ iso2, size = "inline" }: { iso2: string | null | undefined; size?: FlagSize }) {
  const src = flagSrc(iso2);
  if (!src) return null;
  const [width, height] = SIZES[size];
  // eslint-disable-next-line @next/next/no-img-element -- a small static local SVG; next/image would need dangerouslyAllowSVG
  return <img className={`country-flag country-flag--${size}`} src={src} alt="" aria-hidden="true" width={width} height={height} loading="lazy" decoding="async" />;
}
```

Append to the end of `apps/web/app/globals.css`:
```css
/* PUB-023: country flags (CountryFlag). The hairline keeps white flags visible on white cards. */
.country-flag{display:inline-block;vertical-align:-0.15em;margin-right:6px;border-radius:2px;box-shadow:0 0 0 1px rgba(15,23,42,.14);object-fit:cover;flex:none}
.country-flag--inline{width:20px;height:15px}.country-flag--large{width:40px;height:30px;margin-right:0}
```

- [ ] **Step 4: Run them to confirm they pass**

Run: `WEB_TEST "npx vitest run tests/lib/countryFlag.test.ts tests/components/CountryFlag.test.tsx"`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/countryFlag.ts apps/web/components/CountryFlag.tsx apps/web/app/globals.css apps/web/tests/lib/countryFlag.test.ts apps/web/tests/components/CountryFlag.test.tsx
git commit -m "feat(pub-023): CountryFlag component and flagSrc guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: API — `iso2` on public countries, course rows and the country lookup

**Files:**
- Modify: `apps/api/app/schemas.py`, class `CountryOut` (~line 1657)
- Modify: `apps/api/app/api/public.py`, `overseas_courses` (~line 186)
- Modify: `apps/api/app/api/lookups.py`, `countries` (~line 245)
- Test: create `apps/api/tests/test_pub_023_country_flags.py`
- Modify (pinned shapes): `apps/api/tests/test_upc_002_country_master.py` (two tests), `apps/api/tests/test_upc_017_public.py` (line ~34)
- Modify: `docs/architecture/API_CONTRACT.md`, adding `## 12EJ` after `## 12EI`

**Interfaces:**
- Consumes: `Country.iso2` (model, nullable, upper-case).
- Produces, all read-only:
  - `CountryOut.iso2: str | None`, so `GET /api/v1/public/countries[ /{slug} ].country.iso2`;
  - `GET /api/v1/public/overseas-courses` rows gain `country_iso2: str | None`;
  - `GET /api/v1/lookups/countries` items gain `iso2: str | None`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_pub_023_country_flags.py`:
```python
"""PUB-023 (DEC-SCOPE-222): the read-only iso2 fields the web needs to draw a country's flag (API §12EJ)."""

import string
import uuid

import pytest
from sqlalchemy import delete, select

from app.models import Country, OverseasCourse, University
from tests.agn001_helpers import login, mk_user
from tests.test_ovs_001_discovery import _make_country, _make_course, _make_university


async def _free_code(db) -> str:
    """An unassigned two-letter code (X?/Q? are never ISO countries); iso2 is unique and the test DB is shared."""
    taken = set(await db.scalars(select(Country.iso2).where(Country.iso2.is_not(None))))
    return next(a + b for a in "XQ" for b in string.ascii_uppercase if a + b not in taken)


async def _cleanup(db, country) -> None:
    unis = select(University.id).where(University.country_id == country.id)
    await db.execute(delete(OverseasCourse).where(OverseasCourse.university_id.in_(unis)))
    await db.execute(delete(University).where(University.country_id == country.id))
    await db.execute(delete(Country).where(Country.id == country.id))
    await db.commit()


@pytest.mark.asyncio
async def test_public_countries_carry_iso2(client, db_session):
    country = await _make_country(db_session, iso2=await _free_code(db_session))
    try:
        listed = next(c for c in (await client.get("/api/v1/public/countries")).json() if c["slug"] == country.slug)
        assert listed["iso2"] == country.iso2
        detail = (await client.get(f"/api/v1/public/countries/{country.slug}")).json()
        assert detail["country"]["iso2"] == country.iso2
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_a_country_without_a_code_has_null_iso2(client, db_session):  # F3: the web then shows no flag
    country = await _make_country(db_session)
    try:
        listed = next(c for c in (await client.get("/api/v1/public/countries")).json() if c["slug"] == country.slug)
        assert "iso2" in listed and listed["iso2"] is None
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_public_course_rows_carry_country_iso2(client, db_session):
    country = await _make_country(db_session, iso2=await _free_code(db_session))
    try:
        university = await _make_university(db_session, country.id)
        category = f"Flags {uuid.uuid4().hex[:8]}"
        await _make_course(db_session, university.id, category=category)
        rows = (await client.get("/api/v1/public/overseas-courses", params={"category": category})).json()
        assert len(rows) == 1 and rows[0]["country"] == country.name and rows[0]["country_iso2"] == country.iso2
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_country_lookup_items_carry_iso2(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get("/api/v1/lookups/countries", params={"q": "jp"})).json()["items"]
    assert items[0]["label"] == "Japan" and items[0]["iso2"] == "JP" and items[0]["detail"] == "JP · Asia"


@pytest.mark.asyncio
async def test_country_lookup_role_check_is_unchanged(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await client.get("/api/v1/lookups/countries")).status_code == 403
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `API_TEST tests/test_pub_023_country_flags.py`
Expected:
- FAIL: the three `iso2` / `country_iso2` tests fail with `KeyError` or an assertion error.
- PASS: `test_country_lookup_role_check_is_unchanged` already passes.
- If `_make_course` doesn't accept `category=`, it does: it applies `defaults.update(overrides)`.

- [ ] **Step 3: Implement**

`apps/api/app/schemas.py`, in `class CountryOut`, add after `name: str`:
```python
    iso2: str | None = None  # PUB-023 (DEC-SCOPE-222): the web draws the flag from this; null = no flag
```

`apps/api/app/api/public.py`, in `overseas_courses`'s return dict, add `"country_iso2": co.iso2` after `"country": co.name`. The full line becomes:
```python
        {"id": c.id, "title": c.title, "level": c.level, "category": c.category, "duration": c.duration, "tuition_fee": c.tuition_fee, "intake": c.intake, "campus": c.campus, "fee_text": c.fee_text, "intake_text": c.intake_text, "university": u.name, "country": co.name, "country_iso2": co.iso2}
```

`apps/api/app/api/lookups.py`, in `countries`, change the item lambda to:
```python
        lambda row: {"id": row[0].id, "label": row[0].name, "detail": _join(row[0].iso2, row[0].region) or None, "iso2": row[0].iso2},  # PUB-023: picker flag
```

- [ ] **Step 4: Update the three pinned-shape tests (contract change per DEC-SCOPE-222)**

`apps/api/tests/test_upc_002_country_master.py`:
```python
# test_public_list_contract_is_unchanged -- PUB-023 (DEC-SCOPE-222) adds iso2 for the flag; nothing else changes
    assert set(match) == {"id", "slug", "name", "iso2", "overview", "tuition", "living_expenses", "visa_process", "work_opportunities", "post_study_work", "pr_opportunities", "faq"}
```
```python
# test_lookup_finds_japan_by_name_or_code_for_an_overseas_admin -- PUB-023 adds iso2 to each item
    expected = {"id": str(japan.id), "label": japan.name, "detail": "JP · Asia", "iso2": "JP"}
```

`apps/api/tests/test_upc_017_public.py` (~line 34):
```python
    assert set(response.json()[0]) == KEYS | {"university", "country", "country_iso2"} and response.json()[0]["tuition_fee"] == "GBP 18,000"  # PUB-023 adds country_iso2
```

- [ ] **Step 5: Run the feature and regression files**

Run: `API_TEST tests/test_pub_023_country_flags.py tests/test_upc_002_country_master.py tests/test_upc_017_public.py tests/test_ovs_001_discovery.py tests/test_upc_003_public.py tests/test_dtu_001_catalogue.py`
Expected: all PASS.

- [ ] **Step 6: Add API contract §12EJ**

In `docs/architecture/API_CONTRACT.md`, after the `## 12EI.` section:
```markdown
## 12EJ. Country flags (PUB-023) — addendum, 2026-10-14

`DEC-SCOPE-222`. Read-only, additive fields so the web can draw a country's flag from its ISO 3166-1 alpha-2 code. No route, auth or RBAC change; no migration.

| Endpoint | Added field | Notes |
|---|---|---|
| `GET /api/v1/public/countries` and `GET /api/v1/public/countries/{slug}` (`country`) | `iso2: string \| null` | `CountryOut`; null for a country without a code |
| `GET /api/v1/public/overseas-courses` | `country_iso2: string \| null` | beside the existing `country` name |
| `GET /api/v1/lookups/countries` | `iso2: string \| null` on each item | `label` and `detail` unchanged; same roles as before |
```

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/public.py apps/api/app/api/lookups.py apps/api/tests/test_pub_023_country_flags.py apps/api/tests/test_upc_002_country_master.py apps/api/tests/test_upc_017_public.py docs/architecture/API_CONTRACT.md
git commit -m "feat(pub-023): iso2 on public countries, course rows and the country lookup (API 12EJ)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Public pages and the university profile screens

**Files:**
- Modify: `apps/web/lib/types.ts` (type `Country`, line 2)
- Modify: `apps/web/app/overseas/countries/page.tsx` (card, line ~14)
- Modify: `apps/web/app/overseas/countries/[slug]/page.tsx` (`<h1>`)
- Modify: `apps/web/app/overseas/page.tsx` (destination card `<h3>`)
- Modify: `apps/web/app/overseas/courses/page.tsx` (country line, ~line 12)
- Modify: `apps/web/components/UniversityView.tsx` (Facts "Country" row, ~line 57)
- Modify: `apps/web/app/partnership/universities/[id]/page.tsx` (Facts "Country" row, ~line 141)
- Test: `apps/web/tests/components/UniversityView.test.tsx` (add cases)

**Interfaces:**
- Consumes:
  - `CountryFlag` (Task 2);
  - `Country.iso2` and course `country_iso2` from the API (Task 3);
  - `flagSrc` (Task 2), for the 🌍 fallback decision;
  - `UniversityView.country.iso2` and `UniversityRow.country.iso2`, which already exist.
- Produces: `Country` type with `iso2?: string | null`.

- [ ] **Step 1: Write the failing test** (`UniversityView`, which already receives `iso2`)

Add to `apps/web/tests/components/UniversityView.test.tsx`, inside `describe("UniversityView", …)`. The file already defines `profile` (with `country: { name: "United Kingdom", iso2: "GB", region: "UK" }`) and `counselor`, and imports the component as `UniversityViewPanel`.
```tsx
  it("shows the country's flag before its name in the profile (PUB-023)", () => {
    const { container } = render(<UniversityViewPanel view={counselor} />);
    const flag = container.querySelector('img.country-flag[src="/flags/gb.svg"]');
    expect(flag).not.toBeNull();
    expect(flag!.parentElement!.textContent).toContain("United Kingdom");
  });
  it("shows no flag for a country without a code (PUB-023 F3)", () => {
    const view = { ...counselor, university: { ...profile, country: { name: "Testland", iso2: null, region: null } } };
    const { container } = render(<UniversityViewPanel view={view} />);
    expect(container.querySelector("img.country-flag")).toBeNull();
    expect(container.textContent).toContain("Testland");
  });
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `WEB_TEST "npx vitest run tests/components/UniversityView.test.tsx"`
Expected: the two new cases FAIL (no `img.country-flag`). Existing cases PASS.

- [ ] **Step 3: Implement**

`apps/web/lib/types.ts`, type `Country`: add `iso2?:string|null;` after `name:string;` (keep the file's compact style):
```ts
export type Country = { id:string; slug:string; name:string; iso2?:string|null; overview:string; tuition:string; living_expenses:string; visa_process:string[]; work_opportunities:string; post_study_work:string; pr_opportunities:string; faq:{question:string;answer:string}[] };
```

`apps/web/app/overseas/countries/page.tsx`:
- Add the imports.
- Replace `<div className="icon-circle">🌍</div>` in the card. The flag replaces 🌍 only when a flag exists (F3).
```tsx
import CountryFlag from "@/components/CountryFlag";
import {flagSrc} from "@/lib/countryFlag";
// …
    content: <article className="card hover"><div className="icon-circle">{flagSrc(country.iso2) ? <CountryFlag iso2={country.iso2} size="large"/> : "🌍"}</div><h3>{country.name}</h3>{/* …rest unchanged… */}</article>,
```

`apps/web/app/overseas/countries/[slug]/page.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";` to the import line.
- Change `<h1>{c.name}</h1>` to:
```tsx
<h1><CountryFlag iso2={c.iso2} size="large"/> {c.name}</h1>
```

`apps/web/app/overseas/page.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";`.
- In the destination card, change `<h3>{c.name}</h3>` to:
```tsx
<h3><CountryFlag iso2={c.iso2}/>{c.name}</h3>
```

`apps/web/app/overseas/courses/page.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";`.
- In the card, change `<span className="muted">{course.country}</span>` to:
```tsx
<span className="muted"><CountryFlag iso2={course.country_iso2}/>{course.country}</span>
```
Leave `searchText`, `filters` and `sortValues` unchanged.

`apps/web/components/UniversityView.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";`.
- Change the Facts row `["Country", u.country.name],` to:
```tsx
            ["Country", <><CountryFlag iso2={u.country.iso2} />{u.country.name}</>],
```

`apps/web/app/partnership/universities/[id]/page.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";`.
- Change `["Country", u.country.name],` to:
```tsx
              ["Country", <><CountryFlag iso2={u.country.iso2} />{u.country.name}</>],
```

- [ ] **Step 4: Run tests and type-check**

Run: `WEB_TEST "npx vitest run tests/components/UniversityView.test.tsx && npm run typecheck"`
Expected: PASS, and tsc shows no errors. If tsc reports that `u.country.iso2` doesn't exist on the detail page's type, stop and report it. Don't cast.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/app/overseas apps/web/components/UniversityView.tsx "apps/web/app/partnership/universities/[id]/page.tsx" apps/web/tests/components/UniversityView.test.tsx
git commit -m "feat(pub-023): flags on public country/course pages and university profiles

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Country picker options (`SearchableSelect`)

**Files:**
- Modify: `apps/web/lib/lookups.ts` (`PickOption`, line 3)
- Modify: `apps/web/components/SearchableSelect.tsx` (the option `<li>`, ~line 196)
- Test: `apps/web/tests/components/SearchableSelect.test.tsx` (add cases)

**Interfaces:**
- Consumes: `CountryFlag` (Task 2); lookup items with `iso2` (Task 3). `countrySearch` already returns items unchanged.
- Produces: `PickOption = { id: string; label: string; detail?: string | null; iso2?: string | null }`.

- [ ] **Step 1: Write the failing tests**

Add a new `describe` block to `apps/web/tests/components/SearchableSelect.test.tsx`. It uses the file's existing `inForm` helper and `OPTIONS`; focusing the input opens the list, as in the existing cases.
```tsx
describe("SearchableSelect country flags (PUB-023)", () => {
  it("shows a flag before options that carry iso2 (PUB-023)", () => {
    const countries = [{ id: "c1", label: "Japan", detail: "JP · Asia", iso2: "JP" }, { id: "c2", label: "Testland", detail: null, iso2: null }];
    const { input } = inForm(<SearchableSelect label="Country" noun="country" options={countries} />);
    fireEvent.focus(input);
    const options = screen.getAllByRole("option");
    expect(options[0].querySelector('img.country-flag[src="/flags/jp.svg"]')).not.toBeNull();
    expect(options[0].textContent).toBe("Japan — JP · Asia");
    expect(options[1].querySelector("img")).toBeNull();
  });
  it("renders other lookups' options exactly as before (no iso2, no image)", () => {
    const { input } = inForm(<SearchableSelect label="Student" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    for (const option of screen.getAllByRole("option")) expect(option.querySelector("img")).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `WEB_TEST "npx vitest run tests/components/SearchableSelect.test.tsx"`
Expected: the first new case FAILS (no flag img). The rest PASS.

- [ ] **Step 3: Implement**

`apps/web/lib/lookups.ts`:
```ts
export type PickOption = { id: string; label: string; detail?: string | null; iso2?: string | null };  // iso2: PUB-023 country flag
```

`apps/web/components/SearchableSelect.tsx`:
- Add `import CountryFlag from "@/components/CountryFlag";`.
- In the option `<li>`, change `{optionText(option)}` to:
```tsx
            <CountryFlag iso2={option.iso2} />{optionText(option)}
```
The picked value stays in the text `<input>`, so no change there (spec §3.1 amendment).

- [ ] **Step 4: Run tests**

Run: `WEB_TEST "npx vitest run tests/components/SearchableSelect.test.tsx tests/components/UniversityForm.test.tsx"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/lookups.ts apps/web/components/SearchableSelect.tsx apps/web/tests/components/SearchableSelect.test.tsx
git commit -m "feat(pub-023): flags on the country picker's options

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Agent panel and admin lists (table, search, map, global dashboard)

**Files:**
- Modify: `apps/web/components/AgentPartnerUniversitiesPanel.tsx` (lines ~107 and ~166)
- Modify: `apps/web/components/UniversityTable.tsx` (line ~38)
- Modify: `apps/web/app/partnership/search/page.tsx` (line ~168)
- Modify: `apps/web/app/partnership/map/page.tsx` (line ~144)
- Modify: `apps/web/components/GlobalCounts.tsx` (`CountRow`, row header)
- Modify: `apps/web/app/partnership/head/global-dashboard/page.tsx` (`countryRows`, line ~34)
- Test: `apps/web/tests/components/AgentPartnerUniversitiesPanel.test.tsx` (add a case); create `apps/web/tests/components/GlobalCounts.test.tsx`

**Interfaces:**
- Consumes: `CountryFlag` (Task 2). These fields already exist:
  - `AgentPartnerUniversity.country.iso2`
  - `UniversityRow.country.iso2` and `SearchRow`
  - `MapCountry.iso2`
  - `GlobalCountry.iso2`
- Produces: `CountRow = { key: string; label: string; count: number; href?: string; iso2?: string | null }`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/web/tests/components/AgentPartnerUniversitiesPanel.test.tsx`, inside `describe`. Its `item.country` is already `{ id: "c1", name: "United Kingdom", iso2: "GB" }`.
```tsx
  it("shows the country flag in the list (PUB-023)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ items: [item], total: 1 })));
    const { container } = render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    const flag = container.querySelector('td img.country-flag[src="/flags/gb.svg"]');
    expect(flag).not.toBeNull();
    expect(flag!.parentElement!.textContent).toBe("United Kingdom");
  });
```

`apps/web/tests/components/GlobalCounts.test.tsx`:
```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import GlobalCounts from "@/components/GlobalCounts";

afterEach(cleanup);
describe("GlobalCounts", () => {
  it("draws a flag before a country row's label when the row has iso2 (PUB-023)", () => {
    const { container } = render(<GlobalCounts caption="Country-wise" rows={[{ key: "GB", label: "United Kingdom", count: 3, href: "/x", iso2: "GB" }]} />);
    expect(container.querySelector('th img.country-flag[src="/flags/gb.svg"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "United Kingdom" })).toBeTruthy();
  });
  it("leaves rows without iso2 unchanged (other dashboard tables)", () => {
    const { container } = render(<GlobalCounts caption="Stage" rows={[{ key: "s1", label: "Prospect", count: 2 }]} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Prospect" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `WEB_TEST "npx vitest run tests/components/AgentPartnerUniversitiesPanel.test.tsx tests/components/GlobalCounts.test.tsx"`
Expected: the two flag cases FAIL. The others PASS.

- [ ] **Step 3: Implement**

Add `import CountryFlag from "@/components/CountryFlag";` to every file below.

`AgentPartnerUniversitiesPanel.tsx`:
```tsx
              <dt>Country</dt><dd><CountryFlag iso2={detail.country.iso2} />{detail.country.name}</dd>
```
```tsx
                  <td><CountryFlag iso2={u.country.iso2} />{u.country.name}</td>
```

`UniversityTable.tsx`:
```tsx
                <td data-label="Country"><CountryFlag iso2={u.country.iso2} />{u.country.name}</td>
```

`app/partnership/search/page.tsx`:
```tsx
                          <td data-label="Country / city"><span><CountryFlag iso2={u.country.iso2} />{u.country.name} <span className="muted">{u.city}</span></span></td>
```

`app/partnership/map/page.tsx` (~line 144). Keep the swatch, then the flag before the link or name:
```tsx
                          <td data-label="Country"><span><i className={`map-swatch map-${colourOf(c)}`} aria-hidden="true" /> <CountryFlag iso2={c.iso2} />{c.iso2 ? <Link href={countryHref(filters, c.iso2)}>{c.name}</Link> : c.name}</span></td>
```

`components/GlobalCounts.tsx`:
```tsx
import CountryFlag from "@/components/CountryFlag";

export type CountRow = { key: string; label: string; count: number; href?: string; iso2?: string | null };  // iso2: PUB-023 flag (country rows only)
// …
              <th scope="row"><CountryFlag iso2={r.iso2} />{r.href ? <Link href={r.href}>{r.label}</Link> : r.label}</th>
```

`app/partnership/head/global-dashboard/page.tsx`, `countryRows`:
```tsx
  countries.map((c) => ({ key: c.iso2 ?? c.name, label: c.name, count: c.count, href: c.iso2 ? searchHref(status, { iso2: c.iso2 }) : undefined, iso2: c.iso2 }));
```

- [ ] **Step 4: Run tests and type-check**

Run: `WEB_TEST "npx vitest run tests/components/AgentPartnerUniversitiesPanel.test.tsx tests/components/GlobalCounts.test.tsx tests/components/ManagementUniversities.test.tsx && npm run typecheck && npm run lint"`
Expected: PASS, typecheck clean, and lint clean. `UniversityTable`, the search page and the map page have no component test; Task 7's e2e and QA cover them.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentPartnerUniversitiesPanel.tsx apps/web/components/UniversityTable.tsx apps/web/app/partnership/search/page.tsx apps/web/app/partnership/map/page.tsx apps/web/components/GlobalCounts.tsx apps/web/app/partnership/head/global-dashboard/page.tsx apps/web/tests/components/AgentPartnerUniversitiesPanel.test.tsx apps/web/tests/components/GlobalCounts.test.tsx
git commit -m "feat(pub-023): flags in the agent partner list and the partnership admin lists

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Playwright, decision record, backlog and QA note

**Files:**
- Modify: `apps/web/tests/e2e/upc-002-country-master.spec.ts` (append tests)
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-222` after `DEC-SCOPE-221`)
- Modify: `docs/delivery/PUBLIC_SITE_BACKLOG.md` (status row for `PUB-023`; new item `psb-019` for phase 2)
- Create: `docs/quality/PUB-023_EXPLORATORY_QA_2026-10-14.md`

**Interfaces:**
- Consumes: everything above, on a running worktree stack.
- Produces: the e2e evidence and the traceability docs.

- [ ] **Step 1: Write the e2e cases**

Append to `apps/web/tests/e2e/upc-002-country-master.spec.ts`:
```ts
// PUB-023 (DEC-SCOPE-222): each catalogue country card and the country heading show the bundled flag, and the SVG is served.
test("destination cards and the country heading show the country's flag (PUB-023)", async ({ page, request }) => {
  await page.goto("/overseas/countries");
  const search = page.getByLabel("Search destinations");
  await search.fill("United Kingdom");
  const card = page.locator("article.card").filter({ has: page.getByRole("heading", { name: "United Kingdom", exact: true }) });
  await expect(card.locator('img.country-flag[src="/flags/gb.svg"]')).toBeVisible();

  await page.goto("/overseas/countries/united-kingdom");
  await expect(page.locator('h1 img.country-flag[src="/flags/gb.svg"]')).toBeVisible();
  expect((await request.get("/flags/gb.svg")).status()).toBe(200);
});
```

- [ ] **Step 2: Ask the owner to start the worktree stack and run the e2e**

**Ask, don't run.** Send the owner this command (pick free ports, for example web 3023 and API 8023; check them first with `netstat -ano | grep -E ":(3023|8023) "`). The worktree needs a `.env` copied from the main checkout with `API_PORT=8023`, `WEB_PORT=3023` and `FRONTEND_URL=http://localhost:3023`:
```bash
cd "$WT" && cp ../edusphere/.env .env   # then edit API_PORT/WEB_PORT/FRONTEND_URL as above
docker compose -p pub023 -f docker-compose.yml up -d --build
docker compose -p pub023 -f docker-compose.yml exec -T api python -m app.seed
```
After they confirm it is up, run:
```bash
WEB_TEST "E2E_BASE_URL=http://host.docker.internal:3023 npx playwright test tests/e2e/upc-002-country-master.spec.ts tests/e2e/ovs-001-discovery.spec.ts"
```
If the web-test image needs the env var through `-e`, use `-e E2E_BASE_URL=…` (worktree memory). Expected: all PASS. On a failure, open only that test's trace.

- [ ] **Step 3: Exploratory QA and its note**

On the running stack, check each screen in spec §3.1 by eye as the matching role. The seed accounts are `overseasadmin@edusphere.local`, the partnership head, and an agent Master, all with password `Demo@123`. Check:
- the flag is next to the name;
- white flags (JP) are visible against the card;
- countries without a code show no broken image;
- other dropdowns are unchanged;
- the layout on a phone width (375px) still works.

Write `docs/quality/PUB-023_EXPLORATORY_QA_2026-10-14.md`:
```markdown
# PUB-023 Country flags — exploratory QA (2026-10-14)

Stack: worktree `../pub-023`, compose project `pub023`, web :3023. Seeded with `app.seed`.

| # | Screen (spec §3.1) | Role | Result |
|---|---|---|---|
| 1 | /overseas/countries cards | public | <PASS/FAIL + note> |
| 2 | /overseas/countries/united-kingdom heading | public | |
| 3 | /overseas home destination cards | public | |
| 4 | /overseas/courses cards | public | |
| 5 | Agent partner universities list + detail | agent Master | |
| 6 | University Master table | overseas admin | |
| 7 | Partnership search | partnership head | |
| 8 | University detail + view | overseas admin | |
| 9 | Partnership map table | partnership head | |
| 10 | Global dashboard country rows | partnership head | |
| 11 | University form country picker options | overseas admin | |
| 12 | 375px phone width, rows 1–4 | public | |

Findings: <none / list>. `python scripts/check_flag_assets.py`: <output>.
```
Fill in every row with what you actually observed. Fix in-scope findings in the owning task's files and re-run that task's tests.

- [ ] **Step 4: Add `DEC-SCOPE-222` to the decision register**

Append after the `DEC-SCOPE-221` entry in `docs/decisions/PRODUCT_DECISION_REGISTER.md`:
```markdown
### DEC-SCOPE-222 — Country flags, phase 1 (`PUB-023`)

**Evidence:** owner request 2026-10-14 (in-session, after the production launch): "admin country with flag". Answers given directly by the owner in the same session (`EXPLICIT_APPROVAL`). Spec: `docs/superpowers/specs/2026-10-14-pub-023-country-flags-design.md` (approved 2026-10-14, §3.1 amendment reviewed with the plan).

| # | Point | Owner answer |
|---|---|---|
| F1 | Where | All four areas (public, student/agent, admin/staff), in two phases; PUB-023 = phase 1, phase 2 = `psb-019` |
| F2 | Image source | Bundled flag-icons 4:3 SVGs (MIT) under `apps/web/public/flags/`; no emoji, no CDN |
| F3 | No flag available | Show nothing (name only); public country cards keep 🌍 |
| F4 | Accessibility | Decorative (`alt=""`, `aria-hidden`); the name is always beside it |
| F5 | Exclusions | Native `<select>` dropdowns and free-text country fields |

**Numbering:** no migration; API §12EJ; no RBAC change.
**Consequences:** `CountryOut.iso2`, course rows' `country_iso2`, lookup items' `iso2`; `CountryFlag`, `flagSrc`, `PickOption.iso2`, `CountRow.iso2`; `scripts/check_flag_assets.py`; the pinned shape tests in `test_upc_002_country_master.py` and `test_upc_017_public.py` gained the new key.
- **Feature ID authorized:** `PUB-023`. **Status:** see `PUBLIC_SITE_BACKLOG.md`.
```

- [ ] **Step 5: Update `PUBLIC_SITE_BACKLOG.md`**

- In the `## Status` table, add a row after the `psb-001 → PUB-022` row:
```markdown
| `PUB-023` | Country flags, phase 1: public country/course pages, agent partner universities, partnership admin lists, country picker options | `DEC-SCOPE-222` (no migration, API 12EJ) | branch `feature/pub-023` (built; e2e and full suite: owner) |
```
- Change `psb-002 … psb-018` to `psb-002 … psb-019`, in both the title line and the status row.
- Append an item at the end:
```markdown
#### `psb-019` — Country flags, phase 2
- **Why:** PUB-023 (DEC-SCOPE-222 F1) drew flags only where the web already has the country's `iso2`.
- **Gap:** these screens show a country name from their own API, which needs an `iso2` field first:
  - agent shortlist cards (catalogue entries) and the university match / duplicate list;
  - management universities, applications and abroad revenue;
  - partnership courses, opportunities, performance, expected revenue, the pipeline board and the global dashboard university rows;
  - visits and meetings forms and tables; agreements and commission-term forms;
  - BDM organisation detail; the generic `admin/[module]` country column;
  - the agent dashboard, commission report and report filters; the visa checklist.
- **Not in scope:** native `<select>` dropdowns and free-text country fields (F5).
```

- [ ] **Step 6: Final verification**

Run:
```bash
python scripts/check_flag_assets.py
API_TEST tests/test_pub_023_country_flags.py tests/test_upc_002_country_master.py tests/test_upc_017_public.py tests/test_ovs_001_discovery.py tests/test_upc_003_public.py tests/test_dtu_001_catalogue.py
WEB_TEST "npx vitest run tests/lib/countryFlag.test.ts tests/components/CountryFlag.test.tsx tests/components/UniversityView.test.tsx tests/components/SearchableSelect.test.tsx tests/components/UniversityForm.test.tsx tests/components/AgentPartnerUniversitiesPanel.test.tsx tests/components/GlobalCounts.test.tsx tests/components/AgentShortlistForm.test.tsx && npm run typecheck && npm run lint"
```
Expected: everything passes. Report plainly that the full backend suite was **not** run (the owner's standing choice) and list the files that were run.

- [ ] **Step 7: Commit**

```bash
git add apps/web/tests/e2e/upc-002-country-master.spec.ts docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/PUBLIC_SITE_BACKLOG.md docs/quality/PUB-023_EXPLORATORY_QA_2026-10-14.md
git commit -m "docs(pub-023): DEC-SCOPE-222, backlog status + psb-019 phase 2, e2e and QA evidence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Push is the owner's step: `git -C ../pub-023 push -u origin feature/pub-023`.
