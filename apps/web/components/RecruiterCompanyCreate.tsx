"use client";
import { useRouter } from "next/navigation";

import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import { COMPANIES_PATH, VENDORS_PATH } from "@/lib/recruiterCompanies";

// rec-003: after create, open the new company with a status notice (the BdmOrganizationCreate pattern).
export default function RecruiterCompanyCreate({ canChooseRecruiter, withContact = false, vendor = false }: { canChooseRecruiter: boolean; withContact?: boolean; vendor?: boolean }) {
  const router = useRouter();
  return (
    <RecruiterCompanyForm
      mode="create"
      canChooseRecruiter={canChooseRecruiter}
      withContact={withContact}
      initialPartnerType={vendor ? "vendor" : undefined}
      onSaved={(c) => router.push(`${COMPANIES_PATH}/${c.id}?created=1`)}
      onCancel={() => router.push(vendor ? VENDORS_PATH : COMPANIES_PATH)}
    />
  );
}
