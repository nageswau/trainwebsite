"use client";
import { useRouter } from "next/navigation";

import RecruiterRequirementForm from "@/components/RecruiterRequirementForm";
import type { PickOption } from "@/lib/lookups";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";
import { REQUIREMENTS_PATH } from "@/lib/recruiterRequirements";

// rec-007: after create, open the new requirement with a status notice; Cancel goes back where "+ Add" came from (RecruiterCompanyCreate).
export default function RecruiterRequirementCreate({ company, canChooseRecruiter }: { company: PickOption | null; canChooseRecruiter: boolean }) {
  const router = useRouter();
  return (
    <RecruiterRequirementForm
      mode="create"
      company={company}
      canChooseRecruiter={canChooseRecruiter}
      onSaved={(r) => router.push(`${REQUIREMENTS_PATH}/${r.id}?created=1`)}
      onCancel={() => router.push(company ? `${COMPANIES_PATH}/${company.id}` : REQUIREMENTS_PATH)}
    />
  );
}
