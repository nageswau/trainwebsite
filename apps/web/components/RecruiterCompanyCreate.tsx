"use client";
import { useRouter } from "next/navigation";

import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";

// rec-003: after create, open the new company with a status notice (the BdmOrganizationCreate pattern).
export default function RecruiterCompanyCreate({ canChooseRecruiter }: { canChooseRecruiter: boolean }) {
  const router = useRouter();
  return (
    <RecruiterCompanyForm
      mode="create"
      canChooseRecruiter={canChooseRecruiter}
      onSaved={(c) => router.push(`${COMPANIES_PATH}/${c.id}?created=1`)}
      onCancel={() => router.push(COMPANIES_PATH)}
    />
  );
}
