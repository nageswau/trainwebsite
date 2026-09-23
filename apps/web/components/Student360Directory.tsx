import type { PortfolioStudent } from "@/lib/skills";
import { student360Href } from "@/lib/student360Links";

// ENH-013 -- the service roles' way into a student's 360° view: the students of their own school portfolio, as already read by
// their dashboard from /school/portfolio-students (spec §8). The School roles reach the view from the student pages instead.
// With no students it renders nothing: every service dashboard's own panel already says "No students in your portfolio yet.",
// and a second copy of that message broke the sch-004 E2E spec's strict locator (and read as noise).
export default function Student360Directory({ role, students }: { role: string; students: Pick<PortfolioStudent, "id" | "full_name" | "school_name">[] }) {
  if (students.length === 0) return null;
  return (
    <div className="card">
      <h2>Student 360° view</h2>
      <ul className="s360-list">
        {students.map((s) => {
          const href = student360Href(role, s.id);
          return <li key={s.id}>{href ? <a href={href}>{s.full_name}</a> : s.full_name} <span className="muted">{s.school_name}</span></li>;
        })}
      </ul>
    </div>
  );
}
