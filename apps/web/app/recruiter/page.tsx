import { redirect } from "next/navigation";

// rec-001: /recruiter has no page of its own (and is a sign-in `next` target) -- send recruiters to their dashboard.
export default function RecruiterIndex() {
  redirect("/recruiter/dashboard");
}
