import { redirect } from "next/navigation";

// tel-001: /telecaller has no page of its own (and is a sign-in `next` target) -- send telecallers to their dashboard.
export default function TelecallerIndex() {
  redirect("/telecaller/dashboard");
}
