"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

// ENH-013 -- the Career Counselor's Career Passport goal (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md
// §6.2/§8). Same interaction shape as ENH-012's PersonalStatementSection (PortfolioPanel.tsx): an in-flight guard, no optimistic UI,
// the server's own message on failure with the entry kept, router.refresh() to re-read the server's copy on success. The server is
// the authority on who may write; this form is only rendered when the 360 payload says `can_edit_career_goal`.

const MAX = 120;
// Shown when the server gives no usable `detail` (a 5xx, a proxy page): say what failed instead of "Something went wrong."
const NOT_SAVED = "The career goal could not be saved. Please try again.";

// A 200 only counts as saved if it is the record we asked about -- a proxy login page or an empty body must not read as success.
function isSaved(body: unknown): boolean {
  return !!body && typeof body === "object" && "school_student_id" in body && "career_goal" in body;
}

export default function CareerGoalForm({ studentId, goal }: { studentId: string; goal: string | null }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(goal ?? "");
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const inFlight = useRef(false);

  function open() {
    setValue(goal ?? "");
    setAlert(null);
    setSaved(false);
    setEditing(true);
    refocus("career-goal-input");
  }

  function close() {
    setAlert(null);
    setEditing(false);
    refocus("career-goal-edit");
  }

  function fail(message: string) {
    setAlert(message);
    refocus("career-goal-input");
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setAlert(null);
    try {
      let response: Response;
      try {
        response = await fetch(`/api/v1/school/students/${studentId}/career-goal`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ career_goal: value.trim() || null }),
        });
      } catch {
        fail(NOT_COMPLETED);
        return;
      }
      const body = await response.json().catch(() => null);
      if (!response.ok || !isSaved(body)) {
        fail(detailMessage(body?.detail, NOT_SAVED));
        return;
      }
      setSaved(true);
      setEditing(false);
      router.refresh();
      refocus("career-goal-edit");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <>
        <p>{goal ?? <span className="muted">No career goal set yet.</span>}</p>
        <button id="career-goal-edit" type="button" className="btn secondary small" onClick={open}>{goal ? "Edit career goal" : "Set career goal"}</button>
        {saved ? <p className="form-message" role="status">Career goal saved.</p> : null}
      </>
    );
  }
  return (
    <form className="field" onSubmit={save}>
      <label htmlFor="career-goal-input">Career goal</label>
      <input
        id="career-goal-input"
        value={value}
        maxLength={MAX}
        // readOnly, not disabled: refocus() runs on the next animation frame, and a disabled input refuses focus, so after an
        // error focus returned to it only when React had already re-enabled it (browser QA-04). Read-only stays focusable.
        readOnly={busy}
        aria-busy={busy}
        aria-describedby="career-goal-count"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !busy) {  // like the (disabled) Cancel button, not mid-save
            e.preventDefault();
            close();
          }
        }}
      />
      <span id="career-goal-count" className="muted">{value.length} of {MAX} characters</span>
      {alert ? <div role="alert" className="form-error">{alert}</div> : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={close}>Cancel</button>
      </div>
    </form>
  );
}
