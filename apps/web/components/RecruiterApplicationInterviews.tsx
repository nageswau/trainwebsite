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
  const [adding, setAdding] = useState(false);
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
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {data.can_schedule && !adding && (
        <div>
          <button type="button" className="btn secondary small" onClick={() => setAdding(true)}>
            + Schedule interview<span className="visually-hidden"> for {candidateName}</span>
          </button>
        </div>
      )}
      {adding && (
        <RecruiterInterviewForm applicationId={applicationId} contacts={contacts} onCancel={() => setAdding(false)}
          onSaved={(saved, notices) => { setAdding(false); changed([`${saved.round_label} scheduled for ${candidateName}.`, noticeText(notices)].filter(Boolean).join(" ")); }} />
      )}
      {data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>No interviews yet.</p>
      ) : (
        <ul aria-label={`Interviews of ${candidateName}`} style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {data.items.map((i) => <RecruiterInterviewItem key={i.id} interview={i} contacts={contacts} onChanged={(_, notice) => changed(notice)} />)}
        </ul>
      )}
    </div>
  );
}
