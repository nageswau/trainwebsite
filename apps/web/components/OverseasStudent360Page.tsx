import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import CounselorDocumentRequestsPanel from "@/components/CounselorDocumentRequestsPanel";
import CounselorDocumentUpload from "@/components/CounselorDocumentUpload";
import LocalTime from "@/components/LocalTime";
import OverseasStudentFinance from "@/components/OverseasStudentFinance";
import OverseasStudentJourney from "@/components/OverseasStudentJourney";
import PortalShell from "@/components/PortalShell";
import StudentArchiveControls from "@/components/StudentArchiveControls";
import StudentDocumentDownload from "@/components/StudentDocumentDownload";
import StudentMessages from "@/components/StudentMessages";
import StudentNotesPanel from "@/components/StudentNotesPanel";
import StudentProfileForm from "@/components/StudentProfileForm";
import { destinationOptions } from "@/components/StudentProfilePage";
import { ApiError, serverApi } from "@/lib/api";
import { studentMessagesUrl, type StudentMessagesPage } from "@/lib/counselorMessages";
import { formatCalendarDate } from "@/lib/formatDate";
import { PORTAL_NAV } from "@/lib/navigation";
import {
  ACCOUNT_STATUS, STUDENT_TABS, student360Url,
  type StudentActivities, type StudentApplication, type StudentDocumentRow, type StudentFinance, type StudentHistoryItem, type StudentOverview, type StudentTab,
} from "@/lib/overseasStudent360";
import { studentNotesUrl, type StudentNotes } from "@/lib/studentNotes";
import { studentProfileUrl, type StudentProfileResponse } from "@/lib/studentProfile";
import type { User } from "@/lib/types";

const PORTALS = {
  counselor: { nav: "overseas/counselor", roleLabel: "Counselor", back: "/overseas/counselor/students", backLabel: "students" },
  admin: { nav: "overseas/admin", roleLabel: "Overseas Administrator", back: "/overseas/admin/users", backLabel: "users" },
} as const;

type Portal = keyof typeof PORTALS;

/** ccrm-009 (DEC-SCOPE-253): /overseas/{counselor|admin}/students/[id]?tab=... -- one student's 360. ccrm-010's page rules: the API is
 *  the gate and the scope (a student outside the caseload is a 404, another role a 403 card) and each reader stays in their own portal.
 *  B4: link tabs -- only the selected tab's data is fetched; a tab that fails to load says so and leaves the rest of the page working. */
export default async function OverseasStudent360Page({ portal, id, tab }: { portal: Portal; id: string; tab: StudentTab }) {
  const { nav, roleLabel, back, backLabel } = PORTALS[portal];
  let user: User;
  let overview: StudentOverview;
  try {
    [user, overview] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<StudentOverview>(student360Url(id, "overview"))]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // a malformed id is not found, too
    return accessUnavailable(e, "/overseas/login");
  }
  const own = user.role === "overseas_admin" ? "admin" : "counselor";
  if (own !== portal) redirect(`/overseas/${own}/students/${encodeURIComponent(id)}?tab=${tab}`);
  const base = `/overseas/${portal}/students/${encodeURIComponent(id)}`;
  const { student } = overview;
  return (
    <PortalShell nav={PORTAL_NAV[nav] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content student360-page">
        <p><Link href={back}>← Back to {backLabel}</Link></p>
        <h1>{student.full_name}</h1>
        <p className="muted">
          {student.student_code && <>Student ID {student.student_code} · </>}
          {ACCOUNT_STATUS[overview.account_status] ?? overview.account_status}
          {overview.archive && <> · <span className="badge">Archived</span></>}
        </p>
        {/* ccrm-040 (DEC-SCOPE-276): on every tab, so an archived record is never mistaken for a live one */}
        <StudentArchiveControls studentId={student.id} archive={overview.archive} permissions={overview.permissions} />
        <nav aria-label="Student record sections" className="report-tablist">
          {STUDENT_TABS.map((t) => (
            <Link key={t.key} href={`${base}?tab=${t.key}`} className="s360-tab" aria-current={t.key === tab ? "page" : undefined} scroll={false}>
              {t.label}
              {t.key === "applications" && overview.counts.applications > 0 && (
                <>
                  <span className="s360-count" aria-hidden="true">{overview.counts.applications}</span>
                  <span className="visually-hidden">, {overview.counts.applications}</span>
                </>
              )}
            </Link>
          ))}
        </nav>
        <section aria-label={STUDENT_TABS.find((t) => t.key === tab)?.label} className="s360-section">
          {await panel(tab, id, overview, portal)}
        </section>
      </div>
    </PortalShell>
  );
}

async function load<T>(url: string, render: (data: T) => ReactNode | Promise<ReactNode>): Promise<ReactNode> {
  let data: T;
  try {
    data = await serverApi<T>(url);
  } catch {
    return <div className="card form-error" role="alert">This section could not be loaded. Refresh the page to try again.</div>;
  }
  return render(data);
}

async function panel(tab: StudentTab, id: string, overview: StudentOverview, portal: Portal): Promise<ReactNode> {
  switch (tab) {
    case "overview":
      return <OverviewPanel overview={overview} />;
    case "applications":
      return <ApplicationsPanel applications={overview.applications} />;
    case "academic":
    case "preferences":
    case "english":
      return load<StudentProfileResponse>(studentProfileUrl(id), async (data) => (
        <div className="card">
          {/* keyed by tab: each tab starts from the saved profile, never from another tab's unsaved entries */}
          <StudentProfileForm key={tab} initial={data.profile} url={studentProfileUrl(id)} countries={tab === "preferences" ? await destinationOptions() : []} section={tab} />
        </div>
      ));
    case "documents": {
      // ccrm-020: requests can be tied to an application the reader may write (the counselor's own; every one for the Overseas Admin)
      const applications = overview.applications
        .filter((a) => a.open && (portal === "admin" || a.mine))
        .map((a) => ({ id: a.id, label: [a.application_code, a.university, a.course].filter(Boolean).join(" · ") }));
      return (
        <>
          <CounselorDocumentRequestsPanel studentId={id} applications={applications} />
          {/* ccrm-045 (DEC-SCOPE-318): an upload on the student's behalf, tied to the same applications or to none */}
          {!overview.archive && <CounselorDocumentUpload studentId={id} applications={applications} />}
          {await load<{ items: StudentDocumentRow[] }>(student360Url(id, "documents"), (data) => <DocumentsPanel items={data.items} />)}
        </>
      );
    }
    case "finance":
      return load<StudentFinance>(student360Url(id, "finance"), (data) => <OverseasStudentFinance studentId={id} finance={data} />);
    case "activities":
      return (
        <>
          {await load<StudentActivities>(student360Url(id, "activities"), (activities) =>
            load<StudentNotes>(`${studentNotesUrl(id)}?limit=20&offset=0`, (notes) => <ActivitiesPanel activities={activities} notes={notes} />),
          )}
          {/* ccrm-037: its own load, so a failure leaves the rest of the tab working; the card reads the log itself */}
          {await load<StudentMessagesPage>(studentMessagesUrl(id, 1), (data) => (
            <div className="card">
              <h2>Communication</h2>
              <p className="muted">WhatsApp and email with the student, and the replies recorded here — the student and the agent never see this log.</p>
              <StudentMessages studentId={id} recipient={data.recipient} applications={data.applications} canWrite={portal === "counselor"} />
            </div>
          ))}
        </>
      );
    case "history":
      return load<{ items: StudentHistoryItem[] }>(student360Url(id, "history"), (data) => <HistoryPanel items={data.items} />);
  }
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="muted" style={{ margin: 0 }}>{children}</p>;
}

function OverviewPanel({ overview }: { overview: StudentOverview }) {
  const { student, counts } = overview;
  return (
    <>
      <OverseasStudentJourney journey={overview.journey} />
      <div className="card">
        <h2>Contact</h2>
        <dl className="s360-facts">
          <div><dt className="muted">Email</dt><dd>{student.email}</dd></div>
          <div><dt className="muted">Phone</dt><dd>{student.phone || "Not given"}</dd></div>
          <div><dt className="muted">Counselor</dt><dd>{overview.counselor?.full_name ?? "Not assigned"}</dd></div>
          <div><dt className="muted">Account</dt><dd>{ACCOUNT_STATUS[overview.account_status] ?? overview.account_status}</dd></div>
        </dl>
      </div>
      <div className="card">
        <h2>At a glance</h2>
        <dl className="s360-facts">
          <div><dt className="muted">Applications</dt><dd>{counts.applications}</dd></div>
          <div><dt className="muted">Open applications</dt><dd>{counts.open_applications}</dd></div>
          <div><dt className="muted">Documents awaiting review</dt><dd>{counts.documents_to_review}</dd></div>
        </dl>
      </div>
      <ConsentCard consents={overview.consents} />
      <div className="card">
        <h2>Next actions</h2>
        {overview.next_actions.length === 0 ? (
          <Empty>No next actions on open applications.</Empty>
        ) : (
          <ul className="s360-list">
            {overview.next_actions.map((n) => (
              <li key={n.application_id}>
                <strong>{n.university}</strong> {n.application_code && <span className="muted">· {n.application_code}</span>}
                <p>{n.next_action}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

// ccrm-040 (DEC-SCOPE-276 CN4): what the student has agreed to; only the student can give consent.
function ConsentCard({ consents }: { consents: StudentOverview["consents"] }) {
  return (
    <div className="card">
      <h2>Consent</h2>
      {consents.length === 0 ? (
        <Empty>No consent is requested at the moment.</Empty>
      ) : (
        <dl className="s360-facts">
          {consents.map((c) => (
            <div key={c.kind}>
              <dt className="muted">{c.label}</dt>
              <dd>{c.accepted_at ? <>Given <LocalTime value={c.accepted_at} /> ({c.version})</> : "Not yet given — the student is asked on their dashboard"}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function ApplicationsPanel({ applications }: { applications: StudentApplication[] }) {
  if (applications.length === 0) return <div className="card"><Empty>This student has no applications yet.</Empty></div>;
  return (
    <ul className="s360-list">
      {applications.map((a) => (
        <li key={a.id} className="card">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
            <strong>{a.university}</strong>
            <span style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              <span className="status">{a.status_label}</span>
              {a.mine && <span className="badge">Yours</span>}
              {a.is_agency && <span className="badge">Agency</span>}
            </span>
          </div>
          <p className="muted">
            {[a.application_code, a.course, a.intake && `Intake ${a.intake}`].filter(Boolean).join(" · ")}
          </p>
          <dl className="s360-facts">
            {a.sub_status_label && <div><dt className="muted">Sub-status</dt><dd>{a.sub_status_label}</dd></div>}
            {a.outcome_summary && <div><dt className="muted">Outcome</dt><dd>{a.outcome_summary}</dd></div>}
            <div><dt className="muted">Counselor</dt><dd>{a.counselor ?? "Not assigned"}</dd></div>
            <div><dt className="muted">Next action</dt><dd>{a.next_action || "None"}</dd></div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

function DocumentsPanel({ items }: { items: StudentDocumentRow[] }) {
  if (items.length === 0) return <div className="card"><Empty>No documents uploaded yet.</Empty></div>;
  return (
    <ul className="s360-list">
      {items.map((d) => (
        <li key={d.id} className="card">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
            <strong>{d.document_label || d.document_type}</strong>
            <span className="status">{d.status_label}</span>
          </div>
          <p className="muted">
            {d.application_code ?? "Not linked to an application"} · Uploaded <LocalTime value={d.uploaded_at} />
            {d.expiry_date && <> · Expires {formatCalendarDate(d.expiry_date)}</>}
            {d.reviewer && <> · Reviewed by {d.reviewer}{d.reviewed_at && <> on <LocalTime value={d.reviewed_at} /></>}</>}
          </p>
          {d.can_download && <StudentDocumentDownload id={d.id} name={d.document_label || d.document_type} />}
        </li>
      ))}
    </ul>
  );
}

function ActivitiesPanel({ activities, notes }: { activities: StudentActivities; notes: StudentNotes }) {
  return (
    <>
      <div className="card">
        <h2>Notes</h2>
        <p className="muted">Internal notes — the student and the agent never see them.</p>
        <StudentNotesPanel initial={notes} />
      </div>
      <div className="card">
        <h2>Appointments</h2>
        {activities.appointments.length === 0 ? (
          <Empty>No appointments yet.</Empty>
        ) : (
          <ul className="s360-list">
            {activities.appointments.map((a) => (
              <li key={a.id}>
                <strong>{a.type}</strong> <span className="muted">· {a.mode} · {a.status.replace(/_/g, " ")}</span>
                <p><LocalTime value={a.scheduled_at} time label />{a.staff && <> · with {a.staff}</>}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="card">
        <h2>Leads</h2>
        {activities.leads.length === 0 ? (
          <Empty>No lead is linked to this student.</Empty>
        ) : (
          <ul className="s360-list">
            {activities.leads.map((l) => (
              <li key={l.id}>
                {l.href ? <Link href={l.href}><strong>{l.lead_code}</strong></Link> : <strong>{l.lead_code}</strong>} <span className="muted">· {l.stage_label}</span>
                {l.owner && <p className="muted">Owner: {l.owner}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

const KIND_LABEL: Record<StudentHistoryItem["kind"], string> = { status: "Application", audit: "Student record", document: "Document" }; // QA-03

function HistoryPanel({ items }: { items: StudentHistoryItem[] }) {
  if (items.length === 0) return <div className="card"><Empty>Nothing has been recorded yet.</Empty></div>;
  return (
    <ol className="s360-list">
      {items.map((h, i) => (
        <li key={`${h.at}-${i}`}>
          <span className="badge">{KIND_LABEL[h.kind]}</span> <strong>{h.summary}</strong>
          <p className="muted">
            <LocalTime value={h.at} time />
            {h.actor && <> · {h.actor}</>}
            {h.application_code && <> · {h.application_code}</>}
          </p>
          {h.reason && <p>Reason: {h.reason}</p>}
          {h.notes && <p>Notes: {h.notes}</p>}
        </li>
      ))}
    </ol>
  );
}
