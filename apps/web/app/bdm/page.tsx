import { redirect } from "next/navigation";

// bdm-001 QA-09: /bdm has no page of its own (and is a sign-in `next` target) -- send BDMs to My Day.
export default function BdmIndex() {
  redirect("/bdm/my-day");
}
