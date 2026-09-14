"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AvailableBatch } from "@/lib/types";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete enrolment.";
}

// STU-001: "Student browses capacity-aware slot list and books one." The backend's
// GET /workflows/it/batches/available already computes real remaining capacity per
// batch; this replaces the generic WorkflowPanel action (which only offered a bare
// "type in a batch UUID" text field, with no way to actually see what's available) with
// a real picker. Booking a full slot is rejected server-side regardless (DEC-WF-002) --
// this UI only reflects that, it doesn't re-implement the capacity rule.
export default function BatchSlotPicker() {
  const router = useRouter();
  const [batches, setBatches] = useState<AvailableBatch[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [programFilter, setProgramFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/workflows/it/batches/available")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setBatches(data))
      .catch(() => !cancelled && setBatches([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function book(batchId: string) {
    setBusyId(batchId);
    setMessage("");
    setFailed(false);
    const response = await fetch("/api/v1/workflows/it/enrollments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: batchId }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setFailed(true);
      setMessage(detailMessage(data.detail));
      return;
    }
    setMessage(`Enrolment confirmed. Your enrolment reference is ${data.enrollment_code}.`);
    router.refresh();
    // AgreementConsentPanel (STU-009) is a sibling client component with its own fetch;
    // router.refresh() only re-renders server-rendered data, so it won't pick up the new
    // pending_consent enrolment on its own -- nudge it to refetch directly.
    window.dispatchEvent(new Event("edusphere:enrollment-created"));
  }

  if (batches === null) {
    return (
      <div className="action-card">
        <h3>Available batches</h3>
        <p className="muted">Loading available slots…</p>
      </div>
    );
  }

  if (batches.length === 0) {
    return (
      <div className="action-card">
        <h3>Available batches</h3>
        <p className="muted">No batches are currently open for enrolment. Check back soon, or request a callback.</p>
      </div>
    );
  }

  const programs = Array.from(new Set(batches.map((batch) => batch.program))).sort((left, right) => left.localeCompare(right));

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleBatches = batches.filter((batch) => {
    if (programFilter && batch.program !== programFilter) return false;
    if (!normalizedQuery) return true;
    return [batch.program, batch.name, batch.schedule, batch.mode].some((field) => (field ?? "").toLocaleLowerCase().includes(normalizedQuery));
  });

  // Design option 3 (grouped, collapsed by default): with many programs open at
  // once, a flat table is still a long scroll -- grouping by program and collapsing
  // each one lets a student jump straight to the program they care about. A single
  // remaining group (e.g. the program filter below already narrowed to one, or only
  // one program happens to be open) is expanded automatically since there's nothing
  // left to collapse into.
  const groups: { program: string; batches: AvailableBatch[] }[] = [];
  for (const batch of visibleBatches) {
    const group = groups.find((candidate) => candidate.program === batch.program);
    if (group) group.batches.push(batch);
    else groups.push({ program: batch.program, batches: [batch] });
  }
  groups.sort((left, right) => left.program.localeCompare(right.program));

  return (
    <div className="action-card">
      <h3>Choose a trainer/time-slot</h3>
      <p className="muted">
        A slot cannot be changed once booked (fixed for the course duration). Capacity is 20 students per slot.
      </p>
      {/* RAID.md I-25/I-26: the message used to render only after the full batch
          list, so a 409 on a batch far down a long, scrollable list was effectively
          invisible without scrolling all the way down. Rendered here, right below the
          intro text, it's visible regardless of list length or scroll position. */}
      {message && (
        <div className={failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 16 }}>
          {message}
        </div>
      )}
      <div className="table-controls" aria-label="Available slots table controls" style={{ marginTop: 16 }}>
        <div className="table-control-search">
          <label htmlFor="batch-slot-search">Search records</label>
          <input
            id="batch-slot-search"
            className="search"
            type="search"
            placeholder="Search program, batch, schedule…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="batch-slot-program-filter">Program</label>
          <select
            id="batch-slot-program-filter"
            className="select"
            value={programFilter}
            onChange={(event) => setProgramFilter(event.target.value)}
          >
            <option value="">All programs</option>
            {programs.map((program) => (
              <option key={program} value={program}>{program}</option>
            ))}
          </select>
        </div>
      </div>
      {groups.length ? (
        groups.map((group) => (
          <details key={group.program} className="action-card" style={{ marginTop: 16 }} open={groups.length === 1}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>
              {group.program} — {group.batches.length} batch{group.batches.length === 1 ? "" : "es"} open
            </summary>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>Schedule</th>
                    <th>Dates</th>
                    <th>Seats left</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {group.batches.map((batch) => (
                    <tr key={batch.id}>
                      <td>{batch.name}</td>
                      <td>{batch.schedule} · {batch.timezone}</td>
                      <td>{batch.start_date} – {batch.end_date} · {batch.mode}</td>
                      <td>{batch.available} of {batch.capacity}</td>
                      <td>
                        <button className="btn small" disabled={busyId === batch.id || batch.available <= 0} onClick={() => book(batch.id)}>
                          {busyId === batch.id ? "Booking…" : batch.available <= 0 ? "Full" : "Book this slot"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))
      ) : (
        <div className="empty">
          <h3>No matching records</h3>
          <p>Change or clear the search and program filter to see more slots.</p>
        </div>
      )}
    </div>
  );
}
