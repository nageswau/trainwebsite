"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import {
  ADMIN_RULES_API, ADMIN_TASKS_API, apiQuery, HR_REVIEW_STAGES, ownerUrl, PAGE_SIZE, ruleUrl, STAGE_LABELS,
  type HrReviewPage, type HrReviewSummary, type HrRule, type HrRules,
} from "@/lib/hrReviews";

type Notice = { text: string; failed: boolean } | null;

// itc-027 (DEC-SCOPE-353 H3/H5): the IT Admin's HR reviews -- every task (open by default; "needs an owner" = none or deactivated),
// reassignment to an active HR user, and the programme -> HR reviewer rules used for new tasks (no rule = round-robin).
export default function AdminHrReviews() {
  const [rules, setRules] = useState<HrRules | null>(null);
  return (
    <>
      <HrReviewTasks hrUsers={rules?.hr_users ?? null} />
      <HrAssignmentRules rules={rules} setRules={setRules} />
    </>
  );
}

function HrReviewTasks({ hrUsers }: { hrUsers: HrRules["hr_users"] | null }) {
  const [stage, setStage] = useState("");
  const [unassigned, setUnassigned] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<HrReviewPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const response = await fetch(`${ADMIN_TASKS_API}${apiQuery({ stage, page, unassigned })}`, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      setData(await response.json());
    } catch {
      setFailed(true);
    }
  }, [stage, page, unassigned]);

  useEffect(() => { void load(); }, [load]);

  async function assign(task: HrReviewSummary) {
    const target = choice[task.id];
    if (!target || busy) return;
    setBusy(task.id);
    setNotice(null);
    const outcome = await sendJson(ownerUrl(task.id), "PUT", { hr_user_id: target });
    setBusy(null);
    if (!outcome.ok) return setNotice({ text: outcome.message || "The review could not be reassigned.", failed: true });
    const saved = outcome.data as HrReviewSummary;
    setData((current) => current && { ...current, items: current.items.map((t) => (t.id === saved.id ? saved : t)) });
    setNotice({ text: `${saved.student.full_name}'s review is now with ${saved.owner?.full_name}.`, failed: false });
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  return (
    <section className="card" aria-labelledby="hr-review-tasks-title" style={{ marginBottom: 16, display: "grid", gap: 12 }}>
      <div>
        <h3 id="hr-review-tasks-title" style={{ fontSize: 18, marginBottom: 6 }}>Resume reviews</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>A resume a student shares with HR opens one review, owned by the programme&apos;s HR reviewer (or the next HR user in turn). Reassign a review when its owner is away or deactivated.</p>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="hr-review-stage">Stage</label>
          <select id="hr-review-stage" value={stage} onChange={(e) => { setStage(e.target.value); setPage(1); }}>
            <option value="">All open</option>
            {HR_REVIEW_STAGES.map((s) => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
          </select>
        </div>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={unassigned} onChange={(e) => { setUnassigned(e.target.checked); setPage(1); }} /> Needs an owner only
        </label>
      </div>
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>The reviews could not be loaded. <button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button></p>
      ) : !data ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading reviews…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No reviews match.</p>
      ) : (
        <>
          <p className="muted" aria-live="polite" style={{ margin: 0 }}>{data.total} review{data.total === 1 ? "" : "s"}</p>
          <div className="table-wrap">
            <table className="table stack compact hr-reviews" aria-label="Resume reviews">
              <thead><tr><th scope="col">Student</th><th scope="col">Student ID</th><th scope="col">Stage</th><th scope="col">Owner</th><th scope="col">Updated</th><th scope="col">Assign</th></tr></thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id}>
                    <th scope="row" data-label="Student">
                      <Link href={`/it/admin/students/${encodeURIComponent(t.student.id)}/profile`}>{t.student.full_name}</Link>
                    </th>
                    <td data-label="Student ID">{t.student.student_code ?? "—"}</td>
                    <td data-label="Stage">{t.stage_label} · v{t.resume_version}</td>
                    <td data-label="Owner">
                      {t.owner ? t.owner.full_name : <span className="muted">Unassigned</span>}
                      {t.owner && !t.owner.active && <div className="form-error" style={{ fontSize: 13 }}>Deactivated</div>}
                    </td>
                    <td data-label="Updated"><LocalTime value={t.updated_at} /></td>
                    <td data-label="Assign">
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <select aria-label={`Reassign ${t.student.full_name}`} value={choice[t.id] ?? ""} disabled={!hrUsers || busy === t.id}
                                onChange={(e) => setChoice({ ...choice, [t.id]: e.target.value })}>
                          <option value="">Choose HR user</option>
                          {hrUsers?.filter((u) => u.id !== t.owner?.id).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                        </select>
                        <button type="button" className="btn small secondary" disabled={!choice[t.id] || busy === t.id} onClick={() => void assign(t)}>
                          {busy === t.id ? "Assigning…" : "Assign"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <nav aria-label="Review pages" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button type="button" className="btn small secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
              <span className="muted">Page {page} of {pages}</span>
              <button type="button" className="btn small secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

function HrAssignmentRules({ rules, setRules }: { rules: HrRules | null; setRules: (r: HrRules) => void }) {
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(ADMIN_RULES_API, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((body: HrRules) => !cancelled && setRules(body))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [setRules]);

  async function save(rule: HrRule, hrUserId: string) {
    if (!rules || busy) return;
    setBusy(rule.program_id);
    setNotice(null);
    const outcome = await sendJson(ruleUrl(rule.program_id), "PUT", { hr_user_id: hrUserId || null });
    setBusy(null);
    if (!outcome.ok) return setNotice({ text: outcome.message || "The rule could not be saved.", failed: true });
    const saved = outcome.data as HrRule;
    setRules({ ...rules, programs: rules.programs.map((p) => (p.program_id === saved.program_id ? saved : p)) });
    setNotice({ text: saved.hr_user ? `${saved.program}: new reviews go to ${saved.hr_user.full_name}.` : `${saved.program}: new reviews go round-robin.`, failed: false });
  }

  return (
    <section className="card" aria-labelledby="hr-rules-title" style={{ marginBottom: 16, display: "grid", gap: 12 }}>
      <div>
        <h3 id="hr-rules-title" style={{ fontSize: 18, marginBottom: 6 }}>Review assignment rules</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>Choose the HR reviewer for each programme. A student&apos;s newest active enrolment decides; without a rule (or with a deactivated reviewer) reviews go round-robin across active HR users.</p>
      </div>
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>The rules could not be loaded. Refresh the page to try again.</p>
      ) : !rules ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading rules…</p>
      ) : rules.programs.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No programmes yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table stack compact" aria-label="Review assignment rules">
            <thead><tr><th scope="col">Programme</th><th scope="col">HR reviewer</th></tr></thead>
            <tbody>
              {rules.programs.map((p) => (
                <tr key={p.program_id}>
                  <th scope="row" data-label="Programme">{p.program}{!p.active && <div className="muted" style={{ fontSize: 13 }}>Inactive programme</div>}</th>
                  <td data-label="HR reviewer">
                    <select aria-label={`HR reviewer for ${p.program}`} value={p.hr_user?.id ?? ""} disabled={busy === p.program_id} onChange={(e) => void save(p, e.target.value)}>
                      <option value="">Round-robin (no rule)</option>
                      {p.hr_user && !p.hr_user.active && <option value={p.hr_user.id}>{p.hr_user.full_name} (deactivated)</option>}
                      {rules.hr_users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
