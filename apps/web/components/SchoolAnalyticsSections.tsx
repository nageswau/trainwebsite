import SchoolGradePerformance from "@/components/SchoolGradePerformance";
import SchoolScorecardGrid from "@/components/SchoolScorecardGrid";
import SchoolStudentDevelopment from "@/components/SchoolStudentDevelopment";
import SectionUnavailable from "@/components/SectionUnavailable";
import type { SchoolAnalytics } from "@/lib/schoolAnalytics";

// ENH-016: §29, Part B §14 and §28 below the existing report, for the Coordinator and the Principal (D7, D9).
export default function SchoolAnalyticsSections({ data, role }: { data: SchoolAnalytics; role: "coordinator" | "principal" }) {
  const basePath = `/school/${role}/reports`;
  return (
    <div className="portal-content">
      {data.grades ? <SchoolGradePerformance data={data.grades} /> : <SectionUnavailable title="Grade-wise comparison" />}
      <div id="development">
        {data.development ? <SchoolStudentDevelopment data={data.development} basePath={basePath} /> : <SectionUnavailable title="Student development" />}
      </div>
      {data.scorecards ? (
        <SchoolScorecardGrid page={data.scorecards} grade={data.grade} basePath={basePath} studentHref={(id) => `/school/${role}/students/${id}`} />
      ) : (
        <SectionUnavailable title="Student progress scorecards" />
      )}
    </div>
  );
}
