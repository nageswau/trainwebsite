import { serverApi } from "@/lib/api";
import { formatDate } from "@/components/SchoolChildOverview";

// SCH-008 -- narrow Student Journey Timeline: a chronological rail of events already
// recorded for one student, read from GET /school/students/{id}/timeline. That endpoint
// reuses the exact same own-scope loader as SCH-001/007 (own institution, plus
// assigned-only for Teacher and own-child-only for Parent), so this component renders
// correctly for whichever role is looking -- a Parent who calls it always gets their own
// child's events only, never another student's, even at the same school.
//
// The five categories below are the only ones the confirmed data model can produce today
// (`DEC-SCOPE-015`): no Skills/Portfolio/Overseas-progress/Foreign-Language/Test-prep
// stages are shown, because no confirmed module records them yet.

export type TimelineEvent = { date: string; category: "profile" | "career" | "psychometric" | "academic" | "activity"; type: string; title: string; detail: string | null };
export type StudentTimeline = { student: { id: string; full_name: string }; events: TimelineEvent[] };

export async function loadStudentTimeline(studentId: string): Promise<StudentTimeline> {
  return serverApi<StudentTimeline>(`/api/v1/school/students/${studentId}/timeline`);
}

const CATEGORY: Record<TimelineEvent["category"], { label: string; color: string }> = {
  profile: { label: "Profile", color: "#071b38" },
  career: { label: "Career", color: "#0755b9" },
  psychometric: { label: "Psychometric", color: "#0e7c86" },
  academic: { label: "Academic", color: "#6d28d9" },
  activity: { label: "Activity", color: "#15803d" },
};

export default function SchoolStudentTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p className="muted">No journey events recorded yet.</p>;
  }
  return (
    <div className="jtl">
      {events.map((e, i) => {
        const meta = CATEGORY[e.category];
        return (
          <div className="jtl-row" key={`${e.type}-${e.date}-${i}`}>
            <div className="jtl-rail">
              <span className="jtl-node" style={{ "--jtl-color": meta.color } as React.CSSProperties} />
            </div>
            <div className="jtl-body">
              <span className="jtl-date">{formatDate(e.date, true)}</span>
              <span className="jtl-badge" style={{ "--jtl-color": meta.color } as React.CSSProperties}>{meta.label}</span>
              <h4 className="jtl-title">{e.title}</h4>
              {e.detail && <p className="jtl-detail">{e.detail}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
