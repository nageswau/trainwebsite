"use client";
import { useRouter } from "next/navigation";

import BdmOrganizationForm from "@/components/BdmOrganizationForm";

// §12.2 F9: after create, open the new organization with a status notice.
export default function BdmOrganizationCreate() {
  const router = useRouter();
  return (
    <BdmOrganizationForm
      mode="create"
      onSaved={(o) => router.push(`/bdm/organizations/${o.id}?created=1`)}
      onCancel={() => router.push("/bdm/organizations")}
    />
  );
}
