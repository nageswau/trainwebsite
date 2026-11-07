"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { type PoSheet, TARGET_COMPANIES_URL, territoryUrl } from "@/lib/recruiterPoWork";

type Hit = { id: string; code: string; name: string; territory?: string | null };

// pob-009 T4/T5: a PO's territory and this month's target companies. The Team Lead (`manage`) sets the territory, adds companies by
// territory or by name, and removes one; the PO reads the list. The API decides scope and duplicates; each write re-renders the page.
export default function PoTargetCompanies({ sheet, manage }: { sheet: PoSheet; manage: boolean }) {
  const router = useRouter();
  const [territory, setTerritory] = useState(sheet.territory ?? "");
  const [batch, setBatch] = useState(sheet.territory ?? "");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function run(work: () => Promise<{ ok: boolean; message?: string; done?: string }>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    const outcome = await work();
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message ?? "Something went wrong.");
    setNotice(outcome.done ?? "Saved.");
    router.refresh();
  }

  const add = (body: Record<string, unknown>) =>
    run(async () => {
      const r = await sendJson(TARGET_COMPANIES_URL, "POST", { recruiter_user_id: sheet.recruiter.id, month: sheet.month, ...body });
      if (!r.ok) return { ok: false, message: r.message };
      const added = Number(r.data.added ?? 0);
      return { ok: true, done: added === 0 ? "No new company was added (already on the list or none matched)." : `Added ${added} ${added === 1 ? "company" : "companies"}.` };
    });

  async function search(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return setHits(null);
    try {
      const response = await fetch(`/api/v1/recruiter/companies?q=${encodeURIComponent(q)}&limit=10`);
      const data = response.ok ? await response.json() : null;
      setHits(Array.isArray(data?.items) ? data.items : []);
    } catch {
      setError("Unable to search companies right now.");
    }
  }

  const listed = new Set(sheet.target_companies.map((t) => t.company.id));
  return (
    <section className="form-section" aria-labelledby="target-companies-title" style={{ marginTop: 24 }}>
      <h3 id="target-companies-title">Territory and target companies</h3>
      {manage ? (
        <form className="analytics-form" onSubmit={(e) => { e.preventDefault(); void run(async () => {
          const r = await sendJson(territoryUrl(sheet.recruiter.id), "PUT", { territory: territory.trim() || null });
          return r.ok ? { ok: true, done: "Territory saved." } : { ok: false, message: r.message };
        }); }}>
          <div className="field">
            <label htmlFor="po-territory">Territory</label>
            <input id="po-territory" value={territory} maxLength={120} placeholder="Not set" onChange={(e) => setTerritory(e.target.value)} disabled={busy} />
          </div>
          <button className="btn secondary" type="submit" disabled={busy}>Save territory</button>
        </form>
      ) : (
        <p>Territory: <strong>{sheet.territory ?? "Not set"}</strong></p>
      )}
      {manage && sheet.editable && (
        <>
          <form className="analytics-form" onSubmit={(e) => { e.preventDefault(); if (batch.trim()) void add({ territory: batch.trim() }); }}>
            <div className="field">
              <label htmlFor="po-batch-territory">Add every company in territory</label>
              <input id="po-batch-territory" value={batch} maxLength={120} onChange={(e) => setBatch(e.target.value)} disabled={busy} />
            </div>
            <button className="btn secondary" type="submit" disabled={busy || !batch.trim()}>Add by territory</button>
          </form>
          <form className="analytics-form" onSubmit={(e) => void search(e)} role="search">
            <div className="field">
              <label htmlFor="po-company-search">Find a company</label>
              <input id="po-company-search" value={query} maxLength={100} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button className="btn secondary" type="submit">Search</button>
          </form>
          {hits && (hits.length === 0 ? <p className="muted">No company matches.</p> : (
            <ul className="plain-list" aria-label="Matching companies">
              {hits.map((h) => (
                <li key={h.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 4 }}>
                  <span>{h.name} <span className="muted">{h.code}{h.territory ? ` · ${h.territory}` : ""}</span></span>
                  <button className="btn secondary small" type="button" disabled={busy || listed.has(h.id)} onClick={() => void add({ company_ids: [h.id] })}
                    aria-label={`Add ${h.name} to the target list`}>{listed.has(h.id) ? "On the list" : "Add"}</button>
                </li>
              ))}
            </ul>
          ))}
        </>
      )}
      <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {sheet.target_companies.length === 0 ? (
        <p className="empty">No target companies for this month yet.</p>
      ) : (
        <div className="table-scroll" role="region" aria-label="Target companies" tabIndex={0}>
          <table className="table compact stack">
            <thead><tr><th scope="col">Company</th><th scope="col">Territory</th>{manage && sheet.editable && <th scope="col"><span className="visually-hidden">Remove</span></th>}</tr></thead>
            <tbody>
              {sheet.target_companies.map((t) => (
                <tr key={t.id}>
                  <th scope="row"><a href={`/recruiter/companies/${t.company.id}`}>{t.company.name}</a> <span className="muted">{t.company.code}</span></th>
                  <td>{t.company.territory ?? "—"}</td>
                  {manage && sheet.editable && (
                    <td><button className="btn secondary small" type="button" disabled={busy} aria-label={`Remove ${t.company.name}`}
                      onClick={() => void run(async () => {
                        const r = await sendRequest(`${TARGET_COMPANIES_URL}/${t.id}`, { method: "DELETE" });
                        return r.ok ? { ok: true, done: `Removed ${t.company.name}.` } : { ok: false, message: r.message };
                      })}>Remove</button></td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
