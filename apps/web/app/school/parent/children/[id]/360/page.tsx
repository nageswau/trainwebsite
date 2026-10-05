import { renderStudent360Route, type Student360Portal, type Student360RouteProps } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- Parent's Student 360° view, linked children only (enforced by the API).
const PORTAL: Student360Portal = { nav: SCHOOL_NAV.parent, roleLabel: "Parent", backHref: (id) => `/school/parent/children/${id}`, backLabel: "Back to my child" };

export default function SchoolParentChild360Page(props: Student360RouteProps) {
  return renderStudent360Route(PORTAL, props);
}
