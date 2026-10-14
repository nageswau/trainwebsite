"use client";

import CountryFlag from "@/components/CountryFlag";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import UniversityLogo from "./UniversityLogo";
import { formatAgentCommission } from "@/lib/agentCommission";
import { detailMessage } from "@/lib/apiErrors";
import {
  isPartnerDetail,
  isPartnerPage,
  PARTNERS_PAGE_SIZE,
  PARTNERS_URL,
  safeWebsite,
  type PartnerPage,
  type PartnerUniversityDetail,
} from "@/lib/agentPartnerUniversities";

// dtu-001: the published catalogue for an agency. The server decides who sees the agent commission (Masters only); this panel only
// hides a column or field that came back empty. The list and the detail share one panel: the detail is `?id=<uuid>`.
const LINK_STYLE = { color: "var(--blue)", textDecoration: "underline" } as const;
const FAILED = "Unable to load partner universities.";
const SERVER_FAILED = "The server couldn't complete this. Please try again in a moment.";
const fail = (status: number, detail: unknown) => (status >= 500 ? SERVER_FAILED : detailMessage(detail, FAILED));
const text = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? "—" : String(v));

export default function AgentPartnerUniversitiesPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params?.get("id") ?? null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<PartnerPage | null>(null);
  const [detail, setDetail] = useState<PartnerUniversityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(draft.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [draft]);

  useEffect(() => {
    if (selected) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const q = new URLSearchParams({ limit: String(PARTNERS_PAGE_SIZE), offset: String(offset) });
    if (query) q.set("q", query);
    fetch(`${PARTNERS_URL}?${q}`, { signal: controller.signal })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!r.ok || !isPartnerPage(body)) return setError(fail(r.status, body?.detail));
        setPage(body);
      })
      .catch(() => !controller.signal.aborted && setError(FAILED))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [selected, query, offset]);

  useEffect(() => {
    if (!selected) return setDetail(null);
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setDetail(null);
    fetch(`${PARTNERS_URL}/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!r.ok || !isPartnerDetail(body)) return setError(r.status === 404 ? "This university is no longer available." : fail(r.status, body?.detail));
        setDetail(body.university);
      })
      .catch(() => !controller.signal.aborted && setError(FAILED))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [selected]);

  function open(id: string | null) {
    setSelected(id);
    router.replace(id ? `${pathname ?? ""}?id=${encodeURIComponent(id)}` : (pathname ?? ""));
  }

  const alert = error ? <p role="alert">{error}</p> : null;

  if (selected) {
    const website = safeWebsite(detail?.website);
    const showCommission = memberRole === "master" && !!detail && "agent_commission" in detail;
    return (
      <section aria-label="Partner university">
        <p><button type="button" className="btn" onClick={() => open(null)}>Back to partner universities</button></p>
        {alert}
        {loading && !error ? <p>Loading…</p> : null}
        {detail ? (
          <>
            <h2 style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <UniversityLogo name={detail.name} logoUrl={detail.logo_url} size={56} decorative />
              {detail.name}
            </h2>
            <dl>
              <dt>Country</dt><dd><CountryFlag iso2={detail.country.iso2} />{detail.country.name}</dd>
              <dt>Campuses</dt><dd>{detail.campuses.length ? detail.campuses.join(", ") : text(detail.city)}</dd>
              {website ? <><dt>Website</dt><dd><a href={website} target="_blank" rel="noopener noreferrer" style={LINK_STYLE}>{website}</a></dd></> : null}
              {showCommission ? <><dt>Agent commission</dt><dd>{formatAgentCommission(detail.agent_commission)}</dd></> : null}
              {detail.overview ? <><dt>Overview</dt><dd>{detail.overview}</dd></> : null}
              {detail.fee_structure ? <><dt>Fee structure</dt><dd style={{ whiteSpace: "pre-line" }}>{detail.fee_structure}</dd></> : null}
              {detail.deadlines?.length ? <><dt>Deadlines</dt><dd><ul>{detail.deadlines.map((d) => <li key={d}>{d}</li>)}</ul></dd></> : null}
              {detail.scholarships?.length ? <><dt>Scholarships</dt><dd><ul>{detail.scholarships.map((d) => <li key={d}>{d}</li>)}</ul></dd></> : null}
            </dl>
            <h3>Courses ({detail.courses.length})</h3>
            {detail.courses.length === 0 ? (
              <p>No courses listed yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Course</th><th>Level</th><th>Campus</th><th>Fee</th><th>Intake</th></tr></thead>
                  <tbody>
                    {detail.courses.map((c) => (
                      <tr key={c.id}>
                        <td>{c.title}</td><td>{text(c.level)}</td><td>{text(c.campus)}</td>
                        <td>{text(c.fee_text ?? c.tuition_fee)}</td><td>{text(c.intake_text ?? c.intake)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : null}
      </section>
    );
  }

  const items = page?.items ?? [];
  const showCommission = memberRole === "master" && items.some((u) => "agent_commission" in u);
  const total = page?.total ?? 0;
  return (
    <section aria-label="Partner universities">
      <div role="search">
        <label htmlFor="partner-universities-q">Search partner universities</label>{" "}
        <input id="partner-universities-q" type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="University or city" />
      </div>
      {alert}
      {loading && !error ? <p>Loading…</p> : null}
      {!loading && !error && items.length === 0 ? <p>No partner universities found</p> : null}
      {items.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Logo</th><th>University</th><th>Country</th><th>Campuses</th><th>Courses</th>
                {showCommission ? <th>Agent commission</th> : null}
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id}>
                  <td><UniversityLogo name={u.name} logoUrl={u.logo_url} size={36} decorative /></td>
                  <td><button type="button" onClick={() => open(u.id)} style={{ ...LINK_STYLE, background: "none", border: 0, padding: 0, cursor: "pointer", font: "inherit" }}>{u.name}</button></td>
                  <td><CountryFlag iso2={u.country.iso2} />{u.country.name}</td>
                  <td>{u.campuses.length ? u.campuses.join(", ") : text(u.city)}</td>
                  <td>{u.course_count}</td>
                  {showCommission ? <td>{formatAgentCommission(u.agent_commission)}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {total > PARTNERS_PAGE_SIZE ? (
        <p>
          <button type="button" className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PARTNERS_PAGE_SIZE))}>Previous</button>{" "}
          <span>{offset + 1}–{Math.min(offset + PARTNERS_PAGE_SIZE, total)} of {total}</span>{" "}
          <button type="button" className="btn" disabled={offset + PARTNERS_PAGE_SIZE >= total} onClick={() => setOffset(offset + PARTNERS_PAGE_SIZE)}>Next</button>
        </p>
      ) : null}
    </section>
  );
}
