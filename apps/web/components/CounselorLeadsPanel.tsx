"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { isPage, type Page } from "@/lib/apiErrors";
import { COUNSELOR_LEADS_URL, counselorLeadHref, type CounselorLead } from "@/lib/leadHandover";

const PAGE_SIZE = 20;

/** tel-018 (spec §4): the leads handed to this counselor, newest first, 20 a page; the Lead ID opens the lead (return, student link). */
export default function CounselorLeadsPanel({ division }: { division: "it" | "overseas" }) {
  const idp = useId();
  const [page, setPage] = useState<Page<CounselorLead> | "failed" | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${COUNSELOR_LEADS_URL}?${new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })}`, { signal: controller.signal })
      .then(async (response) => {
        const data = response.ok ? await response.json() : null;
        if (!isPage<CounselorLead>(data)) throw new Error(`Request failed (${response.status})`);
        setPage(data);
      })
      .catch(() => controller.signal.aborted || setPage("failed"));
    return () => controller.abort();
  }, [offset, attempt]);

  let body: React.ReactNode;
  if (page === null) body = <p className="muted" role="status">Loading leads…</p>;
  else if (page === "failed") {
    body = (
      <p className="form-error" role="alert">
        Unable to load your leads. <button type="button" className="btn secondary small" onClick={() => { setPage(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  } else if (page.items.length === 0) body = <p className="muted">No leads have been handed to you yet.</p>;
  else {
    body = (
      <>
        <div className="table-wrap workspace" role="region" aria-label="Leads handed to you" tabIndex={0}>
          <table className="table">
            <thead><tr><th scope="col">Lead ID</th><th scope="col">Name</th><th scope="col">Interest</th><th scope="col">Stage</th><th scope="col">Telecaller</th><th scope="col">Lead date</th></tr></thead>
            <tbody>
              {page.items.map((lead) => (
                <tr key={lead.id}>
                  <td><Link href={counselorLeadHref(division, lead.id)}>{lead.lead_code}</Link></td>
                  <td>{lead.name}</td>
                  <td>{lead.subject}</td>
                  <td>{lead.status_label}</td>
                  <td>{lead.telecaller?.full_name ?? <span className="muted">Unassigned</span>}</td>
                  <td><LocalTime value={lead.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav aria-label="Lead pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 13 }}>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
          {page.offset > 0 && <button type="button" className="btn secondary small" onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}>Previous</button>}
          {page.offset + page.items.length < page.total && <button type="button" className="btn secondary small" onClick={() => setOffset(page.offset + PAGE_SIZE)}>Next</button>}
        </nav>
      </>
    );
  }
  return (
    <section aria-labelledby={`${idp}-heading`} className="portal-content" style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Leads</div>
          <h2 id={`${idp}-heading`}>My leads</h2>
          <p className="muted">Leads telecallers handed to you. Open one to link the student account or return it to the telecaller.</p>
        </div>
      </div>
      {body}
    </section>
  );
}
