import { serverApi } from "@/lib/api";
import { formatDate } from "@/components/SchoolChildOverview";

// SCH-008 -- narrow Student Journey Timeline: a chronological rail of events already
// recorded for one student, read from GET /school/students/{id}/timeline. That endpoint
// reuses the exact same own-scope loader as SCH-001/007 (own institution, plus
// assigned-only for Teacher and own-child-only for Parent), so this component renders
// correctly for whichever role is looking -- a Parent who calls it always gets their own
// child's events only, never another student's, even at the same school.
//
// The categories below are the ones `GET /school/students/{id}/timeline` emits today:
// the original five (`DEC-SCOPE-015`) plus test_prep / foreign_language / global_education and (ENH-011) soft_skills / digital_skills,
// which the API began emitting once those modules were linked. A category the API adds later
// must never take the whole student page down, so unknown ones fall back to a neutral badge.

export type TimelineEvent = { date: string; category: "profile" | "career" | "psychometric" | "academic" | "activity" | "test_prep" | "foreign_language" | "global_education" | "soft_skills" | "digital_skills"; type: string; title: string; detail: string | null };
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
  test_prep: { label: "Test prep", color: "#b45309" },
  foreign_language: { label: "Foreign language", color: "#be185d" },
  global_education: { label: "Global education", color: "#0369a1" },
  // ENH-011 (DEC-SCOPE-023): Skills batches. Both colours are over 7:1 against white, like the others.
  soft_skills: { label: "Soft skills", color: "#7c2d12" },
  digital_skills: { label: "Digital skills", color: "#1e3a8a" },
};

const FALLBACK_COLOR = "#475569";

/** Badge for a category the map does not know: "visa_planning" -> "Visa planning". */
function categoryMeta(category: string): { label: string; color: string } {
  const known = (CATEGORY as Record<string, { label: string; color: string } | undefined>)[category];
  if (known) return known;
  const words = category.replace(/_/g, " ").trim();
  return { label: words ? words.charAt(0).toUpperCase() + words.slice(1) : "Other", color: FALLBACK_COLOR };
}

export default function SchoolStudentTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p className="muted">No journey events recorded yet.</p>;
  }
  return (
    <div className="jtl">
      {events.map((e, i) => {
        const meta = categoryMeta(e.category);
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
