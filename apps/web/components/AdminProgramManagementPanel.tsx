"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type AdminProgramRow = { id: string; slug: string; category: string; title: string; duration: string; fees: number; active: boolean };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update program.";
}

// ADM-001: "Admin manages... courses." Create already existed; there was no way at all to
// deactivate/reactivate a program through the UI. Also wires up the new server-side guard
// (ADM-001-AC02): deactivating a program with active/upcoming batches under it is blocked
// until explicitly confirmed here, rather than a silent cascade onto those batches.
export default function AdminProgramManagementPanel() {
  const router = useRouter();
  const [programs, setPrograms] = useState<AdminProgramRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/admin/programs")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setPrograms(data))
      .catch(() => !cancelled && setPrograms([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    if (!programs) return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return programs;
    return programs.filter((p) => p.title.toLowerCase().includes(normalized) || p.category.toLowerCase().includes(normalized) || p.slug.toLowerCase().includes(normalized));
  }, [programs, query]);

  async function toggleActive(row: AdminProgramRow, confirmCascade: boolean) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/admin/programs/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !row.active, ...(confirmCascade ? { confirm_cascade: true } : {}) }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      if (response.status === 409) {
        setConfirmingId(row.id);
        setMessage({ id: row.id, text: `${detailMessage(data.detail)} Click "Confirm deactivate" to proceed anyway.`, failed: true });
        return;
      }
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setConfirmingId(null);
    setMessage({ id: row.id, text: `${row.title} ${row.active ? "deactivated" : "reactivated"}.`, failed: false });
    setPrograms((prev) => (prev ? prev.map((p) => (p.id === row.id ? { ...p, active: !row.active } : p)) : prev));
    router.refresh();
  }

  if (programs === null) {
    return (
      <div className="action-card">
        <h3>Manage programs</h3>
        <p className="muted">Loading programs…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Manage programs</h3>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-program-search">Search by title, category, or slug</label>
        <input id="admin-program-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {visible.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{programs.length === 0 ? "No programs found." : "No programs match this search."}</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Title</th>
                <th scope="col">Category</th>
                <th scope="col">Duration</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.title}</th>
                  <td>{row.category}</td>
                  <td>{row.duration}</td>
                  <td>{row.active ? "Active" : "Inactive"}</td>
                  <td>
                    <button
                      className="btn small"
                      disabled={busyId === row.id}
                      onClick={() => toggleActive(row, confirmingId === row.id)}
                    >
                      {busyId === row.id ? "Saving…" : confirmingId === row.id ? "Confirm deactivate" : row.active ? "Deactivate" : "Reactivate"}
                    </button>
                    {message?.id === row.id && (
                      <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 6, fontSize: 13 }}>
                        {message.text}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
