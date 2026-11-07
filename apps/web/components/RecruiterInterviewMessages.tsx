"use client";
import { useEffect, useState } from "react";

import RecruiterMessages from "@/components/RecruiterMessages";
import { candidateUrl, type CandidateDetail } from "@/lib/recruiterCandidates";
import type { Party } from "@/lib/recruiterMessages";

/** pob-023 (G12, §12): messages to an interview's candidate with the interview as context, so a confirmation or feedback follow-up
 *  template fills its date, time, mode and link. The candidate's number and address come from their record, never typed here. */
export default function RecruiterInterviewMessages({ candidateId, interviewId }: { candidateId: string; interviewId: string }) {
  const [state, setState] = useState<{ party: Party; canWrite: boolean } | "loading" | "failed">("loading");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    fetch(candidateUrl(candidateId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((c: CandidateDetail) => setState({
        party: { kind: "candidate", id: c.id, name: c.name, whatsappTo: c.whatsapp_to ?? null, email: c.email },
        canWrite: c.can_edit && !c.archived_at,
      }))
      .catch(() => controller.signal.aborted || setState("failed"));
    return () => controller.abort();
  }, [candidateId, version]);

  if (state === "loading") return <p className="muted" role="status" style={{ fontSize: 13 }}>Loading the candidate…</p>;
  if (state === "failed") {
    return (
      <div>
        <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the candidate.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
      </div>
    );
  }
  return <RecruiterMessages source={{ kind: "candidate", party: state.party, context: { interviewId } }} canWrite={state.canWrite} />;
}
