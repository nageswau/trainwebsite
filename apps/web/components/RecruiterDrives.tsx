"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import RecruiterDriveForm from "@/components/RecruiterDriveForm";
import { detailMessage } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { collegeText, drivePath, DRIVES_URL, type DriveList, type DriveStatus, EMPTY_DRIVE, isDriveList, PAGE, STATUS_OPTIONS } from "@/lib/recruiterDrives";

/** rec-029: the caller's companies' campus drives, latest first, with a status filter and a search; writers create drives here. */
export default function RecruiterDrives() {
  const router = useRouter();
  const [data, setData] = useState<DriveList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<DriveStatus | "">("");
  const [q, setQ] = useState("");
  const [text, setText] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (status) query.set("status", status);
    if (q) query.set("q", q);
    setError(null);
    fetch(`${DRIVES_URL}?${query}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (response.ok && isDriveList(body)) return setData(body);
        setData(null);
        setError(response.status >= 500 ? "Unable to load drives." : detailMessage(body?.detail, "Unable to load drives."));
      })
      .catch(() => controller.signal.aborted || setError("Unable to load drives. Check your connection and try again."));
    return () => controller.abort();
  }, [status, q, offset, version]);

  function search(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQ(text.trim());
  }

  if (error) {
    return (
      <div className="action-card" role="alert">
        <p style={{ margin: 0 }}>{error}</p>
        <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setVersion((v) => v + 1)}>Try again</button>
      </div>
    );
  }
  if (!data) return <p className="muted" role="status">Loading drives…</p>;
  const filtered = !!status || !!q;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", justifyContent: "space-between" }}>
        <form role="search" onSubmit={search} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="drive-search">Search drives</label>
            <input id="drive-search" type="search" maxLength={200} value={text} onChange={(e) => setText(e.target.value)} placeholder="Drive ID, college, company or role" />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="drive-status">Status</label>
            <select id="drive-status" value={status} onChange={(e) => { setOffset(0); setStatus(e.target.value as DriveStatus | ""); }}>
              <option value="">All</option>
              {STATUS_OPTIONS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
          <button type="submit" className="btn secondary">Search</button>
        </form>
        {data.can_create && !creating && <button type="button" className="btn" onClick={() => setCreating(true)}>+ New drive</button>}
      </div>
      {creating && (
        <RecruiterDriveForm initial={EMPTY_DRIVE} onCancel={() => setCreating(false)} onSaved={(drive) => router.push(drivePath(drive.id))} />
      )}
      {data.items.length === 0 ? (
        <div className="action-card">
          <p style={{ margin: 0 }}>{filtered ? "No drives match these filters." : "No campus drives yet."}</p>
          {!filtered && <p className="muted" style={{ margin: 0 }}>{data.can_create ? "Create a drive to recruit from a college for your company's requirements." : "Drives your recruiters create appear here."}</p>}
        </div>
      ) : (
        <ul aria-label="Campus drives" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(17rem, 1fr))" }}>
          {data.items.map((d) => (
            <li key={d.id} className="action-card" style={{ gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <h3 style={{ margin: 0, fontSize: 18, overflowWrap: "anywhere" }}>
                  <Link href={drivePath(d.id)} style={LINK_STYLE}>{d.code} — {d.job_role}</Link>
                </h3>
                <span className="badge">{d.status_label}</span>
              </div>
              <p style={{ margin: 0, overflowWrap: "anywhere" }}>{collegeText(d.college)}</p>
              <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>{d.company.name} · {formatCalendarDate(d.drive_date)}</p>
              <p style={{ margin: 0, fontSize: 14 }}>
                {d.students_registered} registered · {d.students_attended} attended · {d.vacancies} {d.vacancies === 1 ? "vacancy" : "vacancies"}
              </p>
            </li>
          ))}
        </ul>
      )}
      <Pager label="Drive pages" offset={offset} total={data.total} onOffset={setOffset} />
    </div>
  );
}

/** Previous / Next over PAGE-sized pages; nothing when everything fits on one page. */
export function Pager({ label, offset, total, onOffset }: { label: string; offset: number; total: number; onOffset: (offset: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <nav aria-label={label} className="actions" style={{ gap: 8, alignItems: "center" }}>
      <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - PAGE))}>Previous</button>
      <span className="muted">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
      <button type="button" className="btn secondary small" disabled={offset + PAGE >= total} onClick={() => onOffset(offset + PAGE)}>Next</button>
    </nav>
  );
}
