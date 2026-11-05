"use client";
import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { ORG_TYPE_LABEL, type OrgType } from "@/lib/bdmOrganizations";
import { type CollegeRow, COLLEGES_PATH, COLLEGES_URL } from "@/lib/recruiterColleges";

const PAGE = 25;
const FIELDS = ["q", "course", "pass_out_year", "city"] as const;
type Filters = Record<(typeof FIELDS)[number], string>;
const EMPTY: Filters = { q: "", course: "", pass_out_year: "", city: "" };

// pob-013 (DEC-SCOPE-410 P11): the colleges a placement officer can work with, searched by name, course, graduating year and location.
// The filters apply on Search (one request per search, not per keystroke); a year outside 2000-2100 is refused by the API's own 422.
export default function RecruiterColleges() {
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<CollegeRow> | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let live = true;
    setData(null);
    setFailure(null);
    const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    for (const key of FIELDS) if (filters[key].trim()) query.set(key, filters[key].trim());
    fetch(`${COLLEGES_URL}?${query}`)
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (r.status === 422) throw new Error("Enter a pass-out year from 2000 to 2100.");
        if (!r.ok || !isPage<CollegeRow>(body)) throw new Error("Unable to load colleges.");
        if (live) setData(body);
      })
      .catch((e: Error) => live && setFailure(e.message));
    return () => {
      live = false;
    };
  }, [filters, offset, version]);

  function search(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setFilters({ ...draft });
  }
  const filtered = FIELDS.some((k) => filters[k].trim());

  return (
    <section className="action-card wide telecaller-list" aria-label="Colleges">
      <form className="form" role="search" onSubmit={search} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        {([["q", "Name or code"], ["course", "Course"], ["pass_out_year", "Pass-out year"], ["city", "City or state"]] as const).map(([key, label]) => (
          <div key={key} className="field" style={{ flex: key === "pass_out_year" ? "0 1 140px" : "1 1 180px", margin: 0 }}>
            <label htmlFor={`colleges-${key}`}>{label}</label>
            <input id={`colleges-${key}`} value={draft[key]} inputMode={key === "pass_out_year" ? "numeric" : undefined} maxLength={key === "pass_out_year" ? 4 : 120}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
          </div>
        ))}
        <button type="submit" className="btn small">Search</button>
        {filtered && <button type="button" className="btn secondary small" onClick={() => { setDraft(EMPTY); setFilters(EMPTY); setOffset(0); }}>Clear</button>}
      </form>
      {failure ? (
        <>
          <p className="form-error" role="alert">{failure}</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading colleges…</p>
      ) : data.items.length === 0 ? (
        <p className="empty">{filtered ? "No colleges match these filters." : "No colleges yet. A college BDM adds them in the BDM CRM."}</p>
      ) : (
        <>
          <p className="muted" role="status">{data.total} {data.total === 1 ? "college" : "colleges"}</p>
          <div className="table-wrap" role="region" aria-label="College results" tabIndex={0}>
            <table style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th scope="col">College</th>
                  <th scope="col">Type</th>
                  <th scope="col">Location</th>
                  <th scope="col">Courses</th>
                  <th scope="col">Next pass-out</th>
                  <th scope="col">BDM</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <td data-label="College" style={{ overflowWrap: "anywhere" }}>
                      <Link href={`${COLLEGES_PATH}/${c.id}`}>{c.name}</Link> <span className="muted">{c.code}</span>
                    </td>
                    <td data-label="Type">{ORG_TYPE_LABEL[c.org_type as OrgType] ?? c.org_type}</td>
                    <td data-label="Location">{[c.city, c.state].filter(Boolean).join(", ")}</td>
                    <td data-label="Courses">{c.course_count}</td>
                    <td data-label="Next pass-out">{c.next_pass_out_year ?? "—"}</td>
                    <td data-label="BDM">{c.assigned_bdm_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE && (
            <nav aria-label="College pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset((o) => o + PAGE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
