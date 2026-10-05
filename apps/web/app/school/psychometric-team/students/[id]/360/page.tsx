import { renderStudent360Route, type Student360Portal, type Student360RouteProps } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- Psychometric Team's Student 360° view, own school portfolio only (enforced by the API).
const PORTAL: Student360Portal = { nav: SCHOOL_NAV["psychometric-team"], roleLabel: "Psychometric Team", backHref: () => "/school/psychometric-team/dashboard", backLabel: "Back to dashboard" };

export default function SchoolPsychometricTeamStudent360Page(props: Student360RouteProps) {
  return renderStudent360Route(PORTAL, props);
}
