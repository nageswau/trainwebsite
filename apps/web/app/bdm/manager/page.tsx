import { redirect } from "next/navigation";

// bdm-001 QA-09: /bdm/manager has no page of its own (and is a sign-in `next` target) -- send managers to their dashboard.
export default function BdmManagerIndex() {
  redirect("/bdm/manager/dashboard");
}
