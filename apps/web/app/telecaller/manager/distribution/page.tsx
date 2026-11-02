import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerRulesPanel from "@/components/TelecallerRulesPanel";
import TelecallerStrategyPanel from "@/components/TelecallerStrategyPanel";

// tel-007 (T11, DI3): the routing rules new leads follow -- itc-006: source, then product, then city, then the team's strategy.
export default function TelecallerManagerDistributionPage() {
  return (
    <TelecallerCataloguePage title="Distribution rules" intro="Send new leads from a source, for a product or from a city straight to one of your telecallers. Every other lead goes to the team's active telecallers in turn, or to whoever has the fewest open leads.">
      <TelecallerStrategyPanel />
      <TelecallerRulesPanel />
    </TelecallerCataloguePage>
  );
}
