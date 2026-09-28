import { renderStudent360Route, type Student360Portal, type Student360RouteProps } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- Academic Team's Student 360° view, own school portfolio only (enforced by the API).
// QA24-01: back to the team's student page (its editable Digital Portfolio), as the coordinator's view does.
const PORTAL: Student360Portal = { nav: SCHOOL_NAV["academic-team"], roleLabel: "Academic Team", backHref: (id) => `/school/academic-team/students/${id}`, backLabel: "Back to student" };

export default function SchoolAcademicTeamStudent360Page(props: Student360RouteProps) {
  return renderStudent360Route(PORTAL, props);
}
