# upc-002 — Country master: ISO code, region, full list (design + plan)

Source: `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` upc-002 (U12, `EXPLICIT_APPROVAL` 2026-10-08). Dependencies: none.
Path: **bounded** (extends the existing `countries` table and public catalogue). Session run autonomously; the user pre-authorised
proceeding on recommended answers.

## 1. Decisions

| # | Decision | Authority |
|---|---|---|
| C1 | **Q-06 regions (9):** `UK` (GB only), `Europe` (rest of Europe incl. Ireland, Russia, Cyprus, Crown dependencies), `North America` (US, CA, GL, BM, PM), `Latin America & Caribbean` (incl. Mexico), `Middle East` (AE, BH, IL, IQ, IR, JO, KW, LB, OM, PS, QA, SA, SY, TR, YE), `Asia` (incl. Central Asia and the Caucasus), `Oceania` (AU, NZ, Pacific, CC, CX, UM), `Africa` (incl. Egypt, IO), `Antarctica` (AQ, BV, GS, HM, TF) | User answer 2026-10-08 (`EXPLICIT_APPROVAL`) |
| C2 | `iso2` and `region` are **nullable** in the database, with a unique index on `iso2` and CHECKs on format and region values. The migration fills them for every real row. Reason: 28 test helpers create ad-hoc countries, and every real ISO code is taken, so NOT NULL is infeasible without fake codes | Recommended; backward compatible |
| C3 | `catalogue_visible` defaults to **true** (model and server default), which matches today's behavior: every country row is a catalogue row. The migration inserts the ISO rows explicitly as `false` | Recommended; preserves existing data and behavior |
| C4 | `GET /public/countries` lists only visible rows. `GET /public/countries/{slug}` returns **404** for an internal row (indistinguishable from unknown) | Backlog |
| C5 | `POST /admin/universities` accepts only a **visible** country. An internal one gets the existing `422 Unknown country`. Universities are still all public until upc-003 adds their own flag, so a university in an internal country would leak it | Recommended; closes a leak this item would otherwise open |
| C6 | `GET /lookups/countries?q&limit` lists **all** countries (`{items:[{id,label,detail:"JP · Asia"}],truncated}`) for `overseas_admin` (overseas division) + `super_admin`. Partnership roles are added by upc-001/003 when they exist | Backlog API impact; ENH-031 lookup idiom |
| C7 | **No frontend change.** The only country picker (`AdminUniversityCreatePanel`) creates *catalogue* universities, so per C5 it keeps the 12 visible countries, and a 12-item native select needs no search. The full-list `SearchableSelect` arrives with upc-003's target-university form, which consumes C6 | Deviation from the backlog's "pickers become searchable", recorded here |
| C8 | Seed: `seed/countries.json` rows gain `iso2` + `region`. On a fresh database the migration has already created internal placeholders under the same slugs (`usa`, `dubai-uae` overrides), so the seed **upgrades a placeholder** (`catalogue_visible=false` and empty overview) to catalogue content and sets it visible. It never overwrites a row that already has content | Needed for the fresh-DB order `alembic upgrade` → `seed` |

## 2. Migration `0101_country_master` (after `0100_recruiter_profiles`; drafted as `0100`, re-chained when rec-001 merged first)
1. Guarded `add_column`: `iso2 VARCHAR(2) NULL`, `region VARCHAR(40) NULL`, `catalogue_visible BOOLEAN NOT NULL DEFAULT true`. 0001 builds
   from the current models, so each step checks first.
2. Backfill the 12 catalogue rows by slug → ISO and region (`dubai-uae` → AE / Middle East, `united-kingdom` → GB / UK). Any other
   existing row is left NULL and printed (dev/test rows; there is no country-create API).
3. Pre-check (online): any existing slug that equals a new ISO row's slug, but is not that country, raises loudly.
4. Insert every ISO 3166-1 code not already present as an internal row (empty catalogue text, `catalogue_visible=false`). A plain
   INSERT, so a duplicate code fails loudly.
5. Unique index `uq_countries_iso2`, CHECKs `ck_countries_iso2` (`^[A-Z]{2}$`) and `ck_countries_region`.
- **Downgrade** refuses while any university or scholarship references an internal row, then deletes the internal rows and drops the
  constraints and columns.

## 3. Reviews (Phase 3)
- **API:** the public contract is unchanged (`CountryOut` gains no fields). The lookup follows the ENH-031 contract (auth required,
  403 for wrong role or division, `q` ≤ 100 characters, `limit` 1–50, one log line with counts only). No new write, so no AuditLog.
- **Security:** no IDOR surface (read-only reference data). The public 404 for internal rows avoids revealing the internal list. LIKE
  input is escaped via `_pattern`. Nothing sensitive is logged.
- **Frontend:** none (C7). Regression check is the public catalogue pages plus the admin create panel.
- **Regression risks:** OVS-001, PUB-003 and AGN-007 isolation catalogue tests; VISA-002 interview prep; `seed.py`; any
  `select(Country)` without a filter (only `/public/countries`; the others join through `University`).

## 4. Tasks (TDD)
1. Tests: model/migration parity, ISO data (unique, 249 codes, every region valid, the 12 mapped), round trip in a throwaway DB
   (upgrade inserts internal rows + backfills; downgrade restores).
2. Model columns + constraints + `COUNTRY_REGIONS`; migration.
3. Tests and code: public list/detail visibility filter; admin create rejects an internal country.
4. Tests and code: `GET /lookups/countries`.
5. Seed: `countries.json` iso2/region and placeholder upgrade; tests.
6. Docs: API_CONTRACT §12AJ addendum, DATA_MODEL §6.1 addendum, RBAC note, backlog Q-06 answer.
