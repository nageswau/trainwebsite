import { redirect } from "next/navigation";

// upc-001: /partnership/head has no page of its own -- a head lands on their team (U3).
export default function PartnershipHeadIndex() {
  redirect("/partnership/head/team");
}
