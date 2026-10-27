"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { type CertificateCriteria, criteriaSummary } from "@/lib/certificates";

type Recommendation = { status: "recommended" | "not_ready"; comment: string | null; by: string | null; at: string };
type QueueItem = { enrollment_id: string; student: string; batch: string; program: string; eligible: boolean; criteria: CertificateCriteria; recommendation: Recommendation | null };
type Queue = { can_override: boolean; items: QueueItem[] };
type IssueResult = { issued: { enrollment_id: string }[]; failed: { enrollment_id: string; status_code: number; detail: string }[] };

const QUEUE = "/api/v1/workflows/it/certificates/queue";

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

const plural = (count: number) => `${count} certificate${count === 1 ? "" : "s"}`;

// nehn-031 (DEC-ROLE-003, DEC-SCOPE-297): the coordinator's queue -- learners without a certificate who are eligible or carry the
// trainer's recommendation. Issue one or many; a learner who is not eligible needs the override permission and a written reason.
export default function CoordinatorCertificateQueue() {
  const router = useRouter();
  const [queue, setQueue] = useState<Queue | null>(null);
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  async function load() {
    const response = await fetch(QUEUE).catch(() => null);
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) {
      setBusy(false);
      setLoadError(detailMessage(data?.detail, "The certificate queue could not be loaded."));
      return;
    }
    setLoadError("");
    setQueue(data);
    setSelected([]);
  }

  useEffect(() => {
    void load();
  }, []);

  const items = queue?.items ?? [];
  const selectable = items.filter((item) => item.eligible || queue?.can_override).map((item) => item.enrollment_id);
  const needsOverride = items.some((item) => selected.includes(item.enrollment_id) && !item.eligible);
  const toggle = (id: string, on: boolean) => setSelected((current) => (on ? [...current, id] : current.filter((value) => value !== id)));

  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const reason = String(new FormData(form).get("override_reason") ?? "").trim();
    if (needsOverride && !reason) {
      setFailed(true);
      setMessage("Enter a reason for the override.");
      return;
    }
    setBusy(true);
    setMessage("");
    setFailed(false);
    const body = needsOverride ? { enrollment_ids: selected, override: true, override_reason: reason } : { enrollment_ids: selected, override: false };
    const response = await fetch("/api/v1/workflows/it/certificates/issue", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) {
      setBusy(false);
      setFailed(true);
      setMessage(detailMessage(data?.detail, "The certificates could not be issued."));
      return;
    }
    const result = data as IssueResult;
    const names = new Map(items.map((item) => [item.enrollment_id, item.student]));
    const problems = result.failed.map((item) => `${names.get(item.enrollment_id) ?? item.enrollment_id} — ${item.detail}`);
    setFailed(result.failed.length > 0 && result.issued.length === 0);
    setMessage(`Issued ${plural(result.issued.length)}.${problems.length ? ` ${problems.length} not issued: ${problems.join("; ")}.` : ""}`);
    form.reset();
    await load();
    setBusy(false); // QA31-05: only once the issued learners have left the queue
    router.refresh();
  }

  return (
    <div className="action-card certificate-queue">
      <h3>Certificate queue</h3>
      {!queue && !loadError && <p className="muted">Loading the certificate queue…</p>}
      {loadError && <div className="form-error" role="alert">{loadError}</div>}
      {message && <div className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live="polite">{message}</div>}
      {queue && !items.length && <p className="muted">No learners are waiting for a certificate.</p>}
      {queue && items.length > 0 && (
        <form className="form" onSubmit={issue}>
          {/* QA31-01: the controls come before the table, so a long queue needs no scrolling to issue. */}
          {needsOverride && (
            <div className="field">
              <label htmlFor="certificate-override-reason">Override reason (required: a selected learner is not eligible)</label>
              <textarea id="certificate-override-reason" name="override_reason" maxLength={1000} required />
            </div>
          )}
          <button className="btn" disabled={busy || !selected.length}>{busy ? "Issuing…" : `Issue selected (${selected.length})`}</button>
          <div className="table-scroll">
            <table className="table stack compact">
              <caption className="visually-hidden">Learners waiting for a certificate</caption>
              <thead>
                <tr>
                  <th scope="col">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={selectable.length > 0 && selected.length === selectable.length}
                      disabled={!selectable.length}
                      onChange={(event) => setSelected(event.target.checked ? selectable : [])}
                    />
                  </th>
                  <th scope="col">Learner</th>
                  <th scope="col">Programme · Batch</th>
                  <th scope="col">Eligibility</th>
                  <th scope="col">Trainer recommendation</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.enrollment_id}>
                    <td data-label="Select">
                      <input
                        type="checkbox"
                        aria-label={`Select ${item.student}`}
                        checked={selected.includes(item.enrollment_id)}
                        disabled={!selectable.includes(item.enrollment_id)}
                        title={selectable.includes(item.enrollment_id) ? undefined : "Not eligible, and you do not have permission to override"}
                        onChange={(event) => toggle(item.enrollment_id, event.target.checked)}
                      />
                    </td>
                    <th scope="row" data-label="Learner">{item.student}</th>
                    <td data-label="Programme · Batch">{item.program} · {item.batch}</td>
                    {/* QA31-06: one wrapper per cell, so the stacked phone layout keeps label | value */}
                    <td data-label="Eligibility">
                      <div>
                        <span className={item.eligible ? "status" : "status pending"}>{item.eligible ? "Eligible" : "Not eligible"}</span>
                        <p className="muted">{criteriaSummary(item.criteria)}</p>
                      </div>
                    </td>
                    <td data-label="Trainer recommendation">
                      {item.recommendation ? (
                        <div>
                          <strong>{item.recommendation.status === "recommended" ? `Recommended by ${item.recommendation.by ?? "the trainer"}` : `Not ready (${item.recommendation.by ?? "the trainer"})`}</strong>
                          {item.recommendation.comment && <p className="muted">{item.recommendation.comment}</p>}
                        </div>
                      ) : (
                        <span className="muted">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </form>
      )}
    </div>
  );
}
