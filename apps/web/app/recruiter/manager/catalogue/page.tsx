import { redirect } from "next/navigation";

// rec-002: the catalogue opens on its first tab.
export default function RecruiterCatalogueIndex() {
  redirect("/recruiter/manager/catalogue/lead-sources");
}
