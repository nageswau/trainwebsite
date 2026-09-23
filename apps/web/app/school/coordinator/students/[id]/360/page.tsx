import { renderStudent360Route, type Student360Portal, type Student360RouteProps } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- School Coordinator's Student 360° view, own institution only (enforced by the API).
const PORTAL: Student360Portal = { nav: SCHOOL_NAV.coordinator, roleLabel: "School Coordinator", backHref: (id) => `/school/coordinator/students/${id}`, backLabel: "Back to student" };

export default function SchoolCoordinatorStudent360Page(props: Student360RouteProps) {
  return renderStudent360Route(PORTAL, props);
}
