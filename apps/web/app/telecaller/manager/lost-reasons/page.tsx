import LostReasonsPanel from "@/components/LostReasonsPanel";
import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";

// ccrm-006 (D8): the reasons a lead is closed as Lost or Not Interested with.
export default function TelecallerManagerLostReasonsPage() {
  return (
    <TelecallerCataloguePage title="Lost reasons" intro="The reasons a telecaller, manager or counselor picks when closing a lead as Lost or Not Interested. Deactivate a reason to hide it from the picker — leads already closed with it keep it.">
      <LostReasonsPanel />
    </TelecallerCataloguePage>
  );
}
