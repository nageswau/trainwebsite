"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Page } from "@/lib/apiErrors";
import { stageLabel } from "@/lib/agentApplications";
import { fetchPage, orgUrl, PAGE_SIZE, type NetworkApplication, type NetworkStudent } from "@/lib/agentNetwork";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-022 (DEC-SCOPE-064 N1/N2): one agency's students or applications for Overseas Admin -- read-only, no contact details, and
// every page the server returns is an audited read, so this list is only mounted when the admin asks for it.
type Kind = "students" | "applications";
type StudentStatus = "active" | "archived";
type Row = NetworkStudent | NetworkApplication;
type Loaded = { page: Page<Row>; status: StudentStatus };

export function NetworkPager({ page, label, busy, onPage }: { page: Page<unknown>; label: string; busy: boolean; onPage: (offset: number) => void }) {
  return (
    <nav aria-label={label} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
      <span className="muted" style={{ fontSize: 13 }}>
        Showing {page.offset + 1}–{page.offset + page.items.length} of {page.total}
      </span>
      <button type="button" className="btn secondary small" aria-label="Previous page" disabled={busy || page.offset === 0} onClick={() => onPage(Math.max(0, page.offset - PAGE_SIZE))}>
        Previous
      </button>
      <button type="button" className="btn secondary small" aria-label="Next page" disabled={busy || page.offset + page.items.length >= page.total} onClick={() => onPage(page.offset + PAGE_SIZE)}>
        Next
      </button>
    </nav>
  );
}

export default function AgentNetworkRecords({ orgId, kind }: { orgId: string; kind: Kind }) {
  const [status, setStatus] = useState<StudentStatus>("active");
  const [offset, setOffset] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const seq = useRef(0);
  const focusHeading = useRef(false);
  const focus = useFocusAfterRender();
  const headingId = `agent-network-${kind}`;

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    const query = `${kind === "students" ? `status=${status}&` : ""}limit=${PAGE_SIZE}&offset=${offset}`;
    const result = await fetchPage<Row>(`${orgUrl(orgId, kind)}?${query}`, `Unable to load ${kind}.`);
    if (mine !== seq.current) return; // a newer request owns the screen
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setLoaded({ page: result.page, status });
    if (focusHeading.current) {
      focusHeading.current = false;
      focus(headingId);
    }
  }, [orgId, kind, status, offset, focus, headingId]);

  useEffect(() => {
    void load();
  }, [load, retry]);

  function goTo(next: number) {
    focusHeading.current = true;
    setOffset(next);
  }

  const data = loaded?.page;
  const empty = kind === "applications" ? "No applications yet." : loaded?.status === "archived" ? "No archived students." : "No students yet.";

  return (
    <section className="kpi-group">
      <h3 id={headingId} tabIndex={-1}>
        {kind === "students" ? "Students" : "Applications"}
      </h3>
      {kind === "students" && (
        <div role="group" aria-label="Student status" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
          {(["active", "archived"] as const).map((s) => (
            <button
              key={s}
              type="button"
              className={s === status ? "btn small" : "btn secondary small"}
              aria-pressed={s === status}
              onClick={() => {
                focusHeading.current = true;
                setStatus(s);
                setOffset(0);
              }}
            >
              {s === "active" ? "Active" : "Archived"}
            </button>
          ))}
        </div>
      )}
      {error ? (
        <>
          <p className="form-error" role="alert">
            {error}
          </p>
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>
            Retry
          </button>
        </>
      ) : !data ? (
        <p className="muted" role="status">
          Loading {kind}…
        </p>
      ) : data.items.length === 0 && data.total > 0 ? (
        // A page that emptied while browsing (rows archived or moved meanwhile): the records exist, just not on this page.
        <p className="muted" aria-busy={loading}>
          No {kind} on this page.{" "}
          <button type="button" className="btn secondary small" onClick={() => goTo(0)}>
            Go to the first page
          </button>
        </p>
      ) : data.items.length === 0 ? (
        <p className="muted" aria-busy={loading}>
          {empty}
        </p>
      ) : (
        <>
          {kind === "applications" && (
            // QA22-04: the list shows every application; the agency's Applications figure counts only those not withdrawn.
            <p className="muted" style={{ fontSize: 13 }}>
              Withdrawn applications are listed here; the Applications figure above leaves them out.
            </p>
          )}
          <div className="table-scroll" role="region" aria-labelledby={headingId} tabIndex={0} aria-busy={loading} style={{ opacity: loading ? 0.6 : 1 }}>
            {kind === "students" ? <StudentTable rows={data.items as NetworkStudent[]} /> : <ApplicationTable rows={data.items as NetworkApplication[]} />}
          </div>
          <NetworkPager page={data} label={`${kind === "students" ? "Student" : "Application"} pages`} busy={loading} onPage={goTo} />
        </>
      )}
    </section>
  );
}

function Head({ columns }: { columns: string[] }) {
  return (
    <thead>
      <tr>
        {columns.map((c) => (
          <th scope="col" key={c}>
            {c}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function StudentTable({ rows }: { rows: NetworkStudent[] }) {
  return (
    <table className="table compact stack">
      <Head columns={["Student", "Assigned to", "Login", "Applications", "Added"]} />
      <tbody>
        {rows.map((s) => (
          <tr key={s.id}>
            <th scope="row" style={{ overflowWrap: "anywhere" }}>
              {s.full_name ?? "—"}
            </th>
            <td data-label="Assigned to">{s.assigned_code ?? "Unassigned"}</td>
            <td data-label="Login">{s.has_login ? "Yes" : "No"}</td>
            <td data-label="Applications">{s.applications}</td>
            <td data-label="Added">{formatDate(s.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ApplicationTable({ rows }: { rows: NetworkApplication[] }) {
  return (
    <table className="table compact stack">
      <Head columns={["Student", "University", "Country", "Stage", "Enrolled", "Updated"]} />
      <tbody>
        {rows.map((a) => (
          <tr key={a.id}>
            <th scope="row" style={{ overflowWrap: "anywhere" }}>
              {a.student_name ?? "—"}
            </th>
            <td data-label="University">{a.university}</td>
            <td data-label="Country">{a.country}</td>
            <td data-label="Stage">{stageLabel(a.status)}</td>
            <td data-label="Enrolled">{a.enrollment_date ? formatDate(a.enrollment_date) : "—"}</td>
            <td data-label="Updated">{formatDate(a.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
