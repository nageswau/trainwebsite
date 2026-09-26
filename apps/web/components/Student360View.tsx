import { renderPanel } from "@/components/Student360Panels";
import Student360Tabs, { type TabSummary } from "@/components/Student360Tabs";
import { formatCalendarDate } from "@/lib/formatDate";
import type { Student360 } from "@/lib/student360";
import { isTabKey, TAB_KEYS, TAB_LABELS } from "@/lib/student360Links";

// ENH-013 -- the Student 360° page body shared by all 7 role routes: a header card, then the tabs (spec §8). A server component:
// every panel is rendered here and passed to the client tabs as children, so only the selection runs in the browser.
export default function Student360View({ data, initialTab, backHref, backLabel }: { data: Student360; initialTab?: string; backHref: string; backLabel: string }) {
  const s = data.student;
  const summaries: TabSummary[] = TAB_KEYS.map((key) => ({ key, label: TAB_LABELS[key], status: data.tabs[key].status, count: data.tabs[key].count }));
  const facts = [s.school_name, s.grade_or_class, s.date_of_birth ? `Born ${formatCalendarDate(s.date_of_birth)}` : null].filter(Boolean).join(" · ");
  return (
    <div className="portal-content">
      <div className="card">
        <p className="muted" style={{ margin: 0 }}>Student 360° view</p>
        <h1 style={{ marginTop: 4 }}>{s.full_name}{s.student_code ? <span className="muted" style={{ fontSize: 14 }}> ({s.student_code})</span> : null}</h1>
        {facts ? <p className="muted">{facts}</p> : null}
        <p><strong>Career goal:</strong> {data.career_goal ?? <span className="muted">Not set</span>}</p>
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
      <Student360Tabs tabs={summaries} initialTab={isTabKey(initialTab) ? initialTab : "overview"}>
        {TAB_KEYS.map((key) => <div key={key}>{renderPanel(key, data.tabs[key], data)}</div>)}
      </Student360Tabs>
    </div>
  );
}
