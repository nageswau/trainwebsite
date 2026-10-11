"use client";
import { useEffect, useState } from "react";

import RecruiterInterviewForm, { type ContactOption } from "@/components/RecruiterInterviewForm";
import RecruiterInterviewItem from "@/components/RecruiterInterviewItem";
import { applicationInterviewsUrl, type ApplicationInterviews, isApplicationInterviews, noticeText } from "@/lib/recruiterInterviews";

/** rec-020 (spec §4): one application's interviews on the requirement's candidate row, newest first, with "+ Schedule interview" when the
 *  API allows it (`can_schedule`: a writer, an open application, a live requirement). Every change is reported up, because scheduling
 *  and a decision move the application's status (IV8). */
export default function RecruiterApplicationInterviews({ applicationId, candidateName, contacts, onChanged }: {
  applicationId: string; candidateName: string; contacts: ContactOption[]; onChanged: (notice: string) => void;
}) {
  const [data, setData] = useState<ApplicationInterviews | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState<string | null>(null); // the schedule form's round: "" = blank, a round = rec-021's next-round draft
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(applicationInterviewsUrl(applicationId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isApplicationInterviews(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [applicationId, version]);

  const changed = (notice: string) => {
    reload();
    onChanged(notice);
  };
  if (failed) {
    return (
      <div>
        <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the interviews.</p>
        <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
      </div>
    );
  }
  if (data === null) return <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading interviews…</p>;
  const suggested = data.items[0]?.feedback; // rec-021 FB5: the newest interview's next round, while it is the newest
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {data.can_schedule && adding === null && (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          {suggested?.next_round && (
            <button type="button" className="btn small" onClick={() => setAdding(suggested.next_round)}>
              + Schedule {suggested.next_round_label} (suggested)<span className="visually-hidden"> for {candidateName}</span>
            </button>
          )}
          <button type="button" className="btn secondary small" onClick={() => setAdding("")}>
            + Schedule interview<span className="visually-hidden"> for {candidateName}</span>
          </button>
        </div>
      )}
      {data.can_schedule && adding !== null && (
        <RecruiterInterviewForm key={adding} applicationId={applicationId} draftRound={adding} contacts={contacts} onCancel={() => setAdding(null)}
          onSaved={(saved, notices) => { setAdding(null); changed([`${saved.round_label} scheduled for ${candidateName}.`, noticeText(notices)].filter(Boolean).join(" ")); }} />
      )}
      {data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>No interviews yet.</p>
      ) : (
        <ul aria-label={`Interviews of ${candidateName}`} style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {data.items.map((i) => (
            <RecruiterInterviewItem key={i.id} interview={i} contacts={contacts} onChanged={(_, notice, nextRound) => {
              changed(notice);
              if (nextRound) setAdding(nextRound); // AC2: the next round's draft opens once the list has reloaded
            }} />
          ))}
        </ul>
      )}
    </div>
  );
}
