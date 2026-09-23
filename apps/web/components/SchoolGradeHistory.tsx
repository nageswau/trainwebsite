import { formatDate } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";

// ENH-004 -- a student's grade/academic-year transitions, read from GET /school/students/{id}/grade-history.
// That endpoint reuses the same own-scope loader as the overview and timeline, so this renders correctly
// for whichever role is looking (a Parent gets their own child's history only). It deliberately reuses the
// Journey Timeline's `.jtl-*` rail: a short, dated list that stacks on mobile without horizontal scroll.
// Outcome is stated in text (badge + sentence), never by colour alone.

// ENH-025: `section`/`roll_number` are additive and absent on history recorded before them.
type State = { academic_year_id: string | null; academic_year_label: string | null; grade_level: number | null; grade_or_class: string | null; section?: string | null; roll_number?: string | null };
export type GradeHistoryEntry = { id: string; action: "promoted" | "held_back"; from: State; to: State; created_at: string };
export type StudentGradeHistory = { student: { id: string; full_name: string }; history: GradeHistoryEntry[] };

export async function loadGradeHistory(studentId: string): Promise<StudentGradeHistory> {
  return serverApi<StudentGradeHistory>(`/api/v1/school/students/${studentId}/grade-history`);
}

const OUTCOME: Record<GradeHistoryEntry["action"], { label: string; color: string }> = {
  promoted: { label: "Promoted", color: "#15803d" },
  held_back: { label: "Held back", color: "#b45309" },
};

function gradeText(state: State) {
  return state.grade_or_class || (state.grade_level !== null ? `Grade ${state.grade_level}` : "Grade not set");
}

function summarize(entry: GradeHistoryEntry) {
  return entry.action === "held_back" ? `Kept in ${gradeText(entry.to)}` : `Moved from ${gradeText(entry.from)} to ${gradeText(entry.to)}`;
}

export default function SchoolGradeHistory({ history }: { history: GradeHistoryEntry[] }) {
  if (history.length === 0) {
    return <p className="muted">No promotions recorded yet.</p>;
  }
  return (
    <div className="jtl">
      {history.map((h) => {
        const meta = OUTCOME[h.action];
        return (
          <div className="jtl-row" key={h.id}>
            <div className="jtl-rail">
              <span className="jtl-node" style={{ "--jtl-color": meta.color } as React.CSSProperties} />
            </div>
            <div className="jtl-body">
              <span className="jtl-date">{formatDate(h.created_at, true)}</span>
              <span className="jtl-badge" style={{ "--jtl-color": meta.color } as React.CSSProperties}>{meta.label}</span>
              <h4 className="jtl-title">{summarize(h)}</h4>
              <p className="jtl-detail">Academic year: {h.from.academic_year_label ? `${h.from.academic_year_label} to ` : ""}{h.to.academic_year_label}</p>
              {(h.from.section || h.from.roll_number) && (
                <p className="jtl-detail">Previous section {h.from.section || "-"}, roll number {h.from.roll_number || "-"}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
