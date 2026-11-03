"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { CLOSED, MY_PROGRESS_URL, STATUS_LABEL, weightsSummary, type MyCourse, type MyProgress } from "@/lib/itProgress";

const HOW: Record<MyCourse["mode"], (c: MyCourse) => string> = {
  computed: c => `Worked out from ${weightsSummary(c.weights)}.`,
  override: () => "Set by your trainer.",
  manual: () => "Set by your trainer.",
};

/** itc-022 (DEC-SCOPE-365 P10): the student's own progress on the Course page -- the overall %, how it is worked out, the parts, the
 *  topics covered, and any remediation plan agreed with them. Trainer feedback stays on the Updates page (itc-028 shared notes). */
export default function MyTrainingProgress() {
  const [data, setData] = useState<MyProgress | null>(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const id = useId();

  const load = useCallback(async (signal: { cancelled: boolean }) => {
    setError(false);
    const outcome = await sendRequest(MY_PROGRESS_URL, { method: "GET" });
    if (signal.cancelled) return;
    if (!outcome.ok || !Array.isArray(outcome.data.courses)) return setError(true);
    setData(outcome.data as unknown as MyProgress);
  }, []);

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load, reload]);

  const plans = data?.remediation_plans.filter(p => !CLOSED.includes(p.status)) ?? [];
  return (
    <section aria-labelledby={`${id}-title`} className="card" style={{ display: "grid", gap: 12, marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ margin: 0, fontSize: 18 }}>My progress</h3>
      <div aria-live="polite" aria-busy={data === null && !error} style={{ display: "grid", gap: 16 }}>
        {error ? (
          <div role="alert" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <p className="form-error" style={{ margin: 0 }}>Unable to load your progress.</p>
            <button type="button" className="btn small secondary" onClick={() => setReload(n => n + 1)}>Try again</button>
          </div>
        ) : data === null ? (
          <p className="muted" style={{ margin: 0 }}>Loading your progress…</p>
        ) : data.courses.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>Your progress appears here once you are enrolled in a batch.</p>
        ) : (
          data.courses.map(course => (
            <article key={course.enrollment_id} style={{ display: "grid", gap: 8 }} aria-label={`${course.course} progress`}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
                <strong>{course.course} · {course.batch}</strong>
                <span style={{ fontSize: 22, fontWeight: 700 }}>{course.progress_percent}%</span>
              </div>
              <div role="progressbar" aria-label={`${course.course} overall progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={course.progress_percent}
                style={{ height: 8, borderRadius: 4, background: "var(--line)", overflow: "hidden" }}>
                <div style={{ width: `${course.progress_percent}%`, height: "100%", background: "var(--brand, #2563eb)" }} />
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 14 }}>{HOW[course.mode](course)}</p>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
                {course.topics_total > 0 && <li>Topics: {course.topics_completed} of {course.topics_total} completed</li>}
                <li>Assignments: {course.assignments_graded} of {course.assignments_total} graded</li>
                {course.labs_total > 0 && <li>Labs: {course.labs_graded} of {course.labs_total} graded</li>}
                <li>Assessments: {course.assessments_passed} of {course.assessments_total} passed</li>
              </ul>
              {course.modules.length > 0 && (
                <details>
                  <summary>Topics by module</summary>
                  <ol style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                    {course.modules.map((m, i) => (
                      <li key={i}>
                        {m.title}
                        <ul style={{ paddingLeft: 18, listStyle: "none" }}>
                          {m.topics.map((t, j) => (
                            <li key={j}><span aria-hidden="true">{t.completed ? "✓ " : "○ "}</span>{t.title}<span className="sr-only">{t.completed ? " — completed" : " — not yet"}</span></li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </article>
          ))
        )}
        {plans.length > 0 && (
          <div style={{ display: "grid", gap: 6 }}>
            <h4 style={{ margin: 0 }}>Your support plan</h4>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {plans.map(p => (
                <li key={p.id}>
                  <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p.actions}</span>
                  <span className="muted" style={{ display: "block", fontSize: 13 }}>By {p.due_date}{p.owner_name ? ` · with ${p.owner_name}` : ""} · {STATUS_LABEL[p.status]}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {data && data.courses.length > 0 && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Your trainer&apos;s feedback is on your <Link href="/it/student/updates">Updates</Link> page.</p>}
      </div>
    </section>
  );
}
