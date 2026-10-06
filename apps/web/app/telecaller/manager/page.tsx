import { redirect } from "next/navigation";

// tel-001: /telecaller/manager has no page of its own -- the manager's landing is their team.
export default function TelecallerManagerIndex() {
  redirect("/telecaller/manager/team");
}
