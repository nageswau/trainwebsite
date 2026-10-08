import { redirect } from "next/navigation";

// upc-001: /partnership has no page of its own (and is a sign-in `next` target) -- send managers to their dashboard.
export default function PartnershipIndex() {
  redirect("/partnership/dashboard");
}
