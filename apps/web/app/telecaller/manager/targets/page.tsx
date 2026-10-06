import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerTargetsPanel from "@/components/TelecallerTargetsPanel";

// tel-022 (T28, G1-G3): daily + monthly targets -- team defaults and per-telecaller overrides, effective from a future date.
export default function TelecallerManagerTargetsPage() {
  return (
    <TelecallerCataloguePage title="Targets" intro="Set daily and monthly targets for each team, and override them for your telecallers. A change starts tomorrow or next month at the earliest, so today's and past results keep the targets they had.">
      <TelecallerTargetsPanel />
    </TelecallerCataloguePage>
  );
}
