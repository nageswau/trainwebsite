import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerLeadImports from "@/components/TelecallerLeadImports";

// tel-006 (T15, IM1): CSV lead import per campaign -- for leads from ad platforms and events.
export default function TelecallerManagerImportsPage() {
  return (
    <TelecallerCataloguePage eyebrow="Leads" title="Lead import" intro="Upload a CSV of leads for one campaign. Each row is checked for duplicates: a known person gets the enquiry added to their lead, and new leads are distributed to your team.">
      <TelecallerLeadImports />
    </TelecallerCataloguePage>
  );
}
