import Link from "next/link";

import { serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import { GLYPH, MY_PROGRESS_URL, STATE_CLASS, STATE_LABELS, type MissingDocument, type Progress, type ProgressApplication } from "@/lib/overseasProgress";

// browser QA-01: the global h2 is display-sized; inside the page the section headings stay below the page title.
const H2 = { fontSize: "20px", margin: "0 0 8px" } as const;

function Application({ app }: { app: ProgressApplication }) {
  const headingId = `progress-${app.id}`;
  return (
    <section className="card" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ fontSize: "18px", margin: "0 0 4px", overflowWrap: "anywhere" }}>
        {app.university}
        {app.closed && <> <span className="badge" style={{ marginLeft: 4 }}>Closed</span></>}
      </h3>
      <p className="muted" style={{ margin: 0 }}>
        {app.application_code ?? "No code yet"}
        {app.intake && <> · Intake {app.intake}</>}
      </p>
      <p style={{ margin: "4px 0 8px", fontWeight: 700 }}>Current step: {app.current.label}</p>
      <ol className="jny-steps" aria-label={`Progress of ${app.university}${app.application_code ? ` (${app.application_code})` : ""}`}>
        {app.steps.map((s) => (
          <li key={s.key} className={`jny-step jny-${STATE_CLASS[s.state]}`} aria-current={s.state === "current" ? "step" : undefined}>
            <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
            <span className="jny-name">{s.label}</span>
            <span className="jny-state">{STATE_LABELS[s.state]}</span>
          </li>
        ))}
      </ol>
      {app.note && <p className="muted" style={{ margin: 0 }}>{app.note}</p>}
    </section>
  );
}

function where(d: MissingDocument): string {
  const app = d.university ? `${d.university}${d.application_code ? ` (${d.application_code})` : ""}` : null;
  return [d.source, app, d.status_label].filter(Boolean).join(" · ");
}

/** nehn-033 (DEC-SCOPE-332): the overseas student's one-page overview -- each application's stage, the documents still to upload and
 *  the next actions. Read-only (counselor-controlled, §19 L543); the API is the gate (the student's own rows only). */
export default async function OverseasProgress() {
  let data: Progress;
  try {
    data = await serverApi<Progress>(MY_PROGRESS_URL);
  } catch {
    return <div className="card" role="status">Your progress could not be loaded. Refresh the page to try again.</div>;
  }
  if (!data.applications.length) {
    return (
      <div className="card">
        <p style={{ margin: 0 }}>
          You have no applications yet. <Link href="/overseas/student/applications">Apply to a university</Link>
        </p>
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card" aria-labelledby="progress-actions">
        <h2 id="progress-actions" style={H2}>Next actions</h2>
        {data.next_actions.length ? (
          <ul aria-label="Next actions" style={{ margin: 0, paddingLeft: 20 }}>
            {data.next_actions.map((a, i) => (
              <li key={i} style={{ overflowWrap: "anywhere" }}>{a.href ? <Link href={a.href}>{a.text}</Link> : a.text}</li>
            ))}
          </ul>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Nothing to do right now. Your counselor will update you.</p>
        )}
      </section>
      <section className="card" aria-labelledby="progress-missing">
        <h2 id="progress-missing" style={H2}>Missing documents</h2>
        {data.missing_documents.length ? (
          <ul aria-label="Missing documents" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
            {data.missing_documents.map((d, i) => (
              <li key={i} style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                  <strong>{d.name}</strong>
                  <span className="muted"> {where(d)}</span>
                  {d.due_date && <span className="muted"> · Due {formatCalendarDate(d.due_date)}</span>}
                  {d.overdue && <> <span className="badge" style={{ marginLeft: 2 }}>Overdue</span></>}
                </span>
                <Link className="btn secondary small" href={d.upload_url} aria-label={`Upload ${d.name}`}>Upload</Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted" style={{ margin: 0 }}>No documents are missing.</p>
        )}
      </section>
      <h2 style={{ ...H2, margin: 0 }}>Your applications</h2>
      {data.applications.map((app) => <Application key={app.id} app={app} />)}
    </div>
  );
}
