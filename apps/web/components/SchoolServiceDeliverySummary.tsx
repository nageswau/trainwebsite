import { serverApi } from "@/lib/api";

type Result = { id: string; subject: string; percentage: number | null; grade: string | null };
type CareerRecord = { id: string; record_type: string };
type PsychRecord = { id: string; assessment_type: string; status: string };

// SCH-004/005/006: read-only summary of published results / career-guidance-and-
// counselling / psychometric status, shared across Principal/Coordinator/Teacher/Parent
// dashboards (SCR-SCH-001/002/003/008/009's own documented "plus X" additions). A
// Draft/Verified result never appears here -- the API itself filters to published only.
export default async function SchoolServiceDeliverySummary() {
  let results: Result[] = [];
  let career: CareerRecord[] = [];
  let psychometric: PsychRecord[] = [];
  try {
    [results, career, psychometric] = await Promise.all([
      serverApi<Result[]>("/api/v1/school/results"),
      serverApi<CareerRecord[]>("/api/v1/school/career-records"),
      serverApi<PsychRecord[]>("/api/v1/school/psychometric-records"),
    ]);
  } catch {
    return null; // Own scope may legitimately have none of these -- an honest empty summary, not an error.
  }
  if (results.length === 0 && career.length === 0 && psychometric.length === 0) return null;
  return (
    <div className="card">
      <h2>Results &amp; guidance</h2>
      <p>
        {results.length} published result{results.length === 1 ? "" : "s"}, {career.length} career guidance/counselling record{career.length === 1 ? "" : "s"}, {psychometric.length} psychometric assessment{psychometric.length === 1 ? "" : "s"}.
      </p>
    </div>
  );
}
