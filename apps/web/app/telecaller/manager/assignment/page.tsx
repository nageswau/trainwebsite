import TelecallerAssignmentPanel from "@/components/TelecallerAssignmentPanel";
import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";

// tel-007 (DI4): the unassigned queue and the team's leads, with bulk assign / reassign to a direct report.
export default function TelecallerManagerAssignmentPage() {
  return (
    <TelecallerCataloguePage eyebrow="Leads" title="Lead assignment" intro="Assign waiting leads to your telecallers, or move leads between them.">
      <TelecallerAssignmentPanel />
    </TelecallerCataloguePage>
  );
}
