import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerRulesPanel from "@/components/TelecallerRulesPanel";

// tel-007 (T11, DI3): the routing rules new leads follow -- product, then city, then round robin.
export default function TelecallerManagerDistributionPage() {
  return (
    <TelecallerCataloguePage title="Distribution rules" intro="Send new leads for a product or a city straight to one of your telecallers. Every other lead goes round robin among the team's active telecallers.">
      <TelecallerRulesPanel />
    </TelecallerCataloguePage>
  );
}
