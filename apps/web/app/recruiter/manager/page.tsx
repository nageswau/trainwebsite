import { redirect } from "next/navigation";

// rec-001: /recruiter/manager has no page of its own -- the placement manager's landing is their team.
export default function RecruiterManagerIndex() {
  redirect("/recruiter/manager/team");
}
