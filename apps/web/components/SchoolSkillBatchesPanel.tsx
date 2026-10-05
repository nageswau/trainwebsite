"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import SchoolSkillAlert, { type SkillAlertState } from "@/components/SchoolSkillAlert";
import SchoolSkillBatchForm from "@/components/SchoolSkillBatchForm";
import { isPage, type Page } from "@/lib/apiErrors";
import { MODULE_LABEL, dateRange, type SkillBatch, type SkillBatchStatus, type SkillModule } from "@/lib/skills";
import type { SchoolRef } from "@/lib/transfers";

// ENH-011 spec §7: the counselor's batches. The first page is read on the server, so first paint has no spinner. A filter change
// replaces the rows behind a skeleton (the old rows answer a different question); "Load more" appends and keeps what is on screen.
const URL = "/api/v1/school/career-counselor/skill-batches";
const LIMIT = 25;

function query(module: SkillModule | "", status: SkillBatchStatus | "", offset: number): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (module) params.set("module_type", module);
  if (status) params.set("status", status);
  return `${URL}?${params}`;
}

export default function SchoolSkillBatchesPanel({ initial, schools }: { initial: Page<SkillBatch>; schools: SchoolRef[] }) {
  const [module, setModule] = useState<SkillModule | "">("");
  const [status, setStatus] = useState<SkillBatchStatus | "">("");
  const [items, setItems] = useState(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [loading, setLoading] = useState<"filter" | "more" | null>(null);
  const [alert, setAlert] = useState<SkillAlertState | null>(null);
  const controller = useRef<AbortController | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function load(nextModule: SkillModule | "", nextStatus: SkillBatchStatus | "", offset: number, mode: "filter" | "more") {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setAlert(null);
    setLoading(mode);
    const retry = () => void load(nextModule, nextStatus, 0, "filter");
    try {
      const response = await fetch(query(nextModule, nextStatus, offset), { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (response.status === 401) return setAlert({ text: "Your session has expired.", expired: true });
      if (!response.ok || !isPage<SkillBatch>(data)) return setAlert({ text: "Could not load skills batches.", retry });
      setItems((prev) => (mode === "more" ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setAlert({ text: "Could not load skills batches.", retry });
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }

  if (schools.length === 0) {
    return (
      <div className="portal-content">
        <div className="card empty">
          <h2>You are not assigned to any school yet.</h2>
          <p>Ask an admin to add you to a school&apos;s team. That school&apos;s students can then be enrolled in skills batches here.</p>
        </div>
      </div>
    );
  }

  const filtered = module !== "" || status !== "";
  const skeleton = loading === "filter";
  return (
    <div className="portal-content skills-page">
      <div className="card">
        <h1>Skills batches</h1>
        <p className="muted">Soft Skills and Digital Skills batches at the schools you support.</p>
        <div className="table-controls">
          <div>
            <label htmlFor="skill-filter-module">Module</label>
            <select id="skill-filter-module" className="select" value={module} disabled={loading !== null} onChange={(e) => { const v = e.target.value as SkillModule | ""; setModule(v); void load(v, status, 0, "filter"); }}>
              <option value="">All modules</option>
              <option value="soft_skills">{MODULE_LABEL.soft_skills}</option>
              <option value="digital_skills">{MODULE_LABEL.digital_skills}</option>
            </select>
          </div>
          <div>
            <label htmlFor="skill-filter-status">Status</label>
            <select id="skill-filter-status" className="select" value={status} disabled={loading !== null} onChange={(e) => { const v = e.target.value as SkillBatchStatus | ""; setStatus(v); void load(module, v, 0, "filter"); }}>
              <option value="">Open and closed</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </div>
        </div>
        <SchoolSkillAlert alert={alert} />
        {!skeleton && items.length === 0 && !alert ? (
          <div className="empty">
            {filtered ? <h3>No batches match these filters.</h3> : (
              <>
                <h3>No skills batches yet.</h3>
                <p>Create one below, then enrol students, add sessions to take attendance, and record assessments.</p>
                <button type="button" className="btn secondary small" onClick={() => titleRef.current?.focus()}>Create a batch</button>
              </>
            )}
          </div>
        ) : (
          <>
            <p className="muted" aria-live="polite">Showing {items.length} of {total}</p>
            <ul className="link-list" role="list" aria-label="Skills batches" aria-busy={loading !== null}>
              {skeleton ? [0, 1, 2].map((i) => <li key={i} aria-hidden="true"><div className="skeleton-line" style={{ width: "100%" }} /></li>) : items.map((b) => (
                <li key={b.id}>
                  <div className="who">
                    <Link href={`/school/career-counselor/skills/${b.id}`}><strong>{b.title}</strong></Link>
                    <span>{MODULE_LABEL[b.module_type]} · {b.school.name} · {b.end_date ? "" : "from "}{dateRange(b.start_date, b.end_date)}{b.topic ? ` · ${b.topic}` : ""}</span>
                  </div>
                  <div className="meta">
                    <span className="muted">{b.enrolled_count} enrolled</span>
                    <span className={b.status === "open" ? "status" : "status pending"}>{b.status === "open" ? "Open" : "Closed"}</span>
                  </div>
                </li>
              ))}
            </ul>
            {!skeleton && items.length < total && (
              <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(module, status, items.length, "more")}>
                {loading === "more" ? "Loading…" : "Load more"}
              </button>
            )}
          </>
        )}
      </div>
      <SchoolSkillBatchForm schools={schools} titleRef={titleRef} />
    </div>
  );
}
