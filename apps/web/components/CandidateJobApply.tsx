"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { applyUrl, type JobCard } from "@/lib/candidateJobs";

// hrc-027 (DEC-SCOPE-398 J7): one job's apply action. The server decides (404 not open, 409 already applied, 422 a requirement not met);
// the card disables the button with the same reasons before a click. A second click while sending is ignored.
export default function CandidateJobApply({ job }: { job: JobCard }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(job.application);

  async function apply() {
    if (busy) return;
    setBusy(true);
    setError("");
    const outcome = await sendJson(applyUrl(job.id), "POST", {});
    setBusy(false);
    if (!outcome.ok) {
      setError((outcome.status ?? 0) >= 500 || !outcome.status ? "We couldn't send your application. Please try again." : outcome.message);
      if (outcome.status === 409 || outcome.status === 404) router.refresh();
      return;
    }
    setApplied({ code: String(outcome.data.code), status_label: String(outcome.data.status_label) });
    router.refresh();
  }

  if (applied) {
    return (
      <p className="form-message" role="status">
        Applied · <strong>{applied.code}</strong> · {applied.status_label}
      </p>
    );
  }
  const reasonId = `job-${job.id}-blocked`;
  return (
    <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
      {job.blocked.length > 0 && (
        <p id={reasonId} className="muted" style={{ margin: 0 }}>
          This job needs {job.blocked.join("; ")}. Update your profile or ask your recruiter.
        </p>
      )}
      <button
        className="btn" type="button" disabled={busy || !job.can_apply} aria-describedby={job.blocked.length ? reasonId : undefined}
        onClick={() => void apply()}
      >
        {busy ? "Applying…" : "Apply"}
      </button>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
    </div>
  );
}
