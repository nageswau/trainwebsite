import TelecallerCampaignsPanel from "@/components/TelecallerCampaignsPanel";
import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";

// tel-002 (T16): marketing campaigns -- source → product → campaign, so reports can show which campaigns bring admissions.
export default function TelecallerManagerCampaignsPage() {
  return (
    <TelecallerCataloguePage title="Campaigns" intro="Each campaign names its source and product, for example Instagram → Cyber Security → September 2026. Deactivate a campaign to hide it from pickers — leads that use it keep it.">
      <TelecallerCampaignsPanel />
    </TelecallerCataloguePage>
  );
}
