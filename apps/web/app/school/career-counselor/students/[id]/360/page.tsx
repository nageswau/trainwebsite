import { renderStudent360Route, type Student360Portal, type Student360RouteProps } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- Career Counselor's Student 360° view, own school portfolio only (enforced by the API).
const PORTAL: Student360Portal = { nav: SCHOOL_NAV["career-counselor"], roleLabel: "Career Counselor", backHref: () => "/school/career-counselor/dashboard", backLabel: "Back to dashboard" };

export default function SchoolCareerCounselorStudent360Page(props: Student360RouteProps) {
  return renderStudent360Route(PORTAL, props);
}
