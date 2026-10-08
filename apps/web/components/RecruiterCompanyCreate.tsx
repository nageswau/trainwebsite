"use client";
import { useRouter } from "next/navigation";

import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";

// rec-003: after create, open the new company with a status notice (the BdmOrganizationCreate pattern).
export default function RecruiterCompanyCreate({ canChooseRecruiter, withContact = false }: { canChooseRecruiter: boolean; withContact?: boolean }) {
  const router = useRouter();
  return (
    <RecruiterCompanyForm
      mode="create"
      canChooseRecruiter={canChooseRecruiter}
      withContact={withContact}
      onSaved={(c) => router.push(`${COMPANIES_PATH}/${c.id}?created=1`)}
      onCancel={() => router.push(COMPANIES_PATH)}
    />
  );
}
