"use client";
import { useRef, useState } from "react";

import BdmLeadForm from "@/components/BdmLeadForm";
import LocalTime from "@/components/LocalTime";
import { isPage, type Page } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { type Lead, orgLeadsPageUrl } from "@/lib/bdmLeads";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const STATUS_LABEL: Record<string, string> = { new: "New", contacted: "Contacted", qualified: "Qualified", converted: "Converted", lost: "Lost" };

// bdm-017 (spec §6; L6 mirrors bdm-009 V5): the organization's student leads, newest first, for anyone who can read it. The heading
// carries the exact total (AC4). A save is applied locally (no refetch), and the notice goes to the profile's one live region (`onNotice`).
// `null` = the server page could not read the first page.
export default function BdmOrganizationLeads({
  organizationId, initial, canAdd, onNotice,
}: { organizationId: string; initial: Page<Lead> | null; canAdd: boolean; onNotice: (text: string, focusStatus?: boolean) => void }) {
  const [items, setItems] = useState(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [loaded, setLoaded] = useState(initial !== null);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const fetched = useRef(initial?.items.length ?? 0); // rows read from the server: Load more's offset (a local insert never moves it)
  const focus = useFocusAfterRender();
  const headingId = `org-${organizationId}-leads`;
  const addId = `org-${organizationId}-add-lead`;

  async function load(offset: number) {
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(orgLeadsPageUrl(organizationId, offset));
      const data = response.ok ? await response.json() : null;
      if (!isPage<Lead>(data)) throw new Error("bad page");
      fetched.current = offset + data.items.length;
      setItems((current) => (offset === 0 ? data.items : appendUnique(current, data.items)));
      setTotal(data.total);
      setLoaded(true);
    } catch {
      setFailure(offset === 0 ? "Leads couldn't be loaded." : "More leads couldn't be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div className="portal-title" style={{ gap: 12, flexWrap: "wrap" }}>
        <h3 id={headingId}>Leads ({total})</h3>
        {canAdd && !adding && (
          <button id={addId} type="button" className="btn small" onClick={() => { setAdding(true); onNotice(""); }}>Add lead</button>
        )}
      </div>
      {adding && (
        <BdmLeadForm organizationId={organizationId}
          onSaved={(lead) => { setItems((current) => [lead, ...current]); setTotal((t) => t + 1); setAdding(false); onNotice("Lead added.", true); }}
          onCancel={() => { setAdding(false); focus(addId); }} />
      )}
      {!loaded ? (
        <div role="alert">
          <p className="form-error">Leads couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      ) : items.length === 0 ? (
        <p className="muted">No leads yet.</p>
      ) : (
        <div className="table-scroll"> {/* QA17-01: its row headers keep their case (an email is never shown in capitals) */}
          <table className="table" aria-label="Leads">
            <thead>
              <tr>
                <th scope="col">Student</th>
                <th scope="col">Interest</th>
                <th scope="col">Status</th>
                <th scope="col">Added by</th>
                <th scope="col">Added</th>
              </tr>
            </thead>
            <tbody>
              {items.map((lead) => (
                <tr key={lead.id}>
                  <th scope="row">
                    {lead.name}
                    <div className="muted" style={{ fontWeight: 400, overflowWrap: "anywhere" }}>{[lead.email, lead.phone].filter(Boolean).join(" · ")}</div>
                  </th>
                  <td>{lead.interest}</td>
                  <td>
                    {STATUS_LABEL[lead.status] ?? lead.status}
                    {lead.converted && <div><span className="badge">Converted to a student</span></div>}
                  </td>
                  <td>{lead.bdm.full_name}</td>
                  <td><LocalTime value={lead.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {loaded && failure && <p className="form-error" role="alert">{failure}</p>}
      {loaded && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(fetched.current)} disabled={loading}>{loading ? "Loading…" : "Load more"}</button>
      )}
    </section>
  );
}
