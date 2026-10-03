"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { stageLabel } from "@/lib/agentApplications";
import { currentStep, isJourney, journeyUrl, STATE_LABELS, STEP_LABELS, type Journey, type JourneyStep } from "@/lib/agentJourney";

const UNABLE = "Unable to load the journey.";
const GLYPH: Record<string, string> = { done: "✓", in_progress: "•", not_started: "–", not_required: "✓", refunded: "↺", refused: "✕", withdrawn: "✕" };

type Failure = { text: string; expired: boolean };

function Steps({ label, steps }: { label: string; steps: JourneyStep[] }) {
  const current = currentStep(steps);
  return (
    <ol className="jny-steps" aria-label={label}>
      {steps.map((s) => (
        <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.key === current ? "step" : undefined}>
          <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state] ?? "–"}</span>
          <span className="jny-name">{STEP_LABELS[s.key] ?? s.key}</span>
          <span className="jny-state">{STATE_LABELS[s.state] ?? s.state}</span>
        </li>
      ))}
    </ol>
  );
}

// AGN-015 (DEC-SCOPE-060 §4, §7): steps 1-4 once for the student, steps 5-9 per application -- state as text, never colour alone.
// Read on open and whenever the student changes (refreshKey); only the newest request may update the screen. A failure is inline
// text with its own retry, not role="alert", so the detail panel's alerts stay the only ones on screen.
export default function AgentStudentJourney({ studentId, refreshKey }: { studentId: string; refreshKey?: string }) {
  const [data, setData] = useState<Journey | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const latest = useRef(0);
  const headingId = `journey-${studentId}`;

  const load = useCallback(() => {
    const request = ++latest.current;
    setFailure(null);
    fetch(journeyUrl(studentId))
      .then(async (response): Promise<Failure | null> => {
        if (response.status === 401) return { text: SESSION_EXPIRED, expired: true };
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok || !isJourney(body)) return { text: UNABLE, expired: false };
        if (request === latest.current) setData(body);
        return null;
      })
      .catch((): Failure => ({ text: UNABLE, expired: false })) // a dropped connection (TypeError)
      .then((failed) => {
        if (failed && request === latest.current) setFailure(failed);
      });
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <section aria-labelledby={headingId} className="jny" style={{ marginTop: 16 }}>
      <h5 id={headingId} style={{ fontSize: "18px", margin: "0 0 8px" }}>Journey</h5>
      {failure ? (
        failure.expired ? (
          <p className="form-error">{failure.text} <Link href={SIGN_IN_PATH}>Sign in again</Link></p>
        ) : (
          <p className="form-error">
            {failure.text}{" "}
            <button type="button" className="btn secondary small" onClick={load}>Try again</button>
          </p>
        )
      ) : data === null ? (
        <p className="muted" role="status">Loading journey…</p>
      ) : (
        <>
          <Steps label="Student steps" steps={data.steps} />
          {data.applications.length === 0 ? (
            <p className="muted">No applications yet.</p>
          ) : (
            data.applications.map((a) => {
              const university = a.university ?? "Unknown university";
              return (
                <div key={a.id}>
                  <p className="jny-caption">{[university, a.intake, stageLabel(a.status)].join(" · ")}</p>
                  <Steps label={`Steps for ${university}`} steps={a.steps} />
                </div>
              );
            })
          )}
        </>
      )}
    </section>
  );
}
