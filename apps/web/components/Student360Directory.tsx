import type { PortfolioStudent } from "@/lib/skills";
import { student360Href } from "@/lib/student360Links";

// ENH-013 -- the service roles' way into a student's 360° view: the students of their own school portfolio, as already read by
// their dashboard from /school/portfolio-students (spec §8). The School roles reach the view from the student pages instead.
export default function Student360Directory({ role, students }: { role: string; students: Pick<PortfolioStudent, "id" | "full_name" | "school_name">[] }) {
  return (
    <div className="card">
      <h2>Student 360° view</h2>
      {students.length === 0 ? (
        <p className="empty" role="status">No students in your portfolio yet.</p>
      ) : (
        <ul className="s360-list">
          {students.map((s) => {
            const href = student360Href(role, s.id);
            return <li key={s.id}>{href ? <a href={href}>{s.full_name}</a> : s.full_name} <span className="muted">{s.school_name}</span></li>;
          })}
        </ul>
      )}
    </div>
  );
}
