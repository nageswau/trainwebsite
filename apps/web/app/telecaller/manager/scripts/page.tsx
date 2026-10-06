import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerScriptsPanel from "@/components/TelecallerScriptsPanel";

// tel-012 (EVID-019 §6, C3): the standard call script per product.
export default function TelecallerManagerScriptsPage() {
  return (
    <TelecallerCataloguePage title="Call scripts" intro="The standard steps a telecaller follows on a call, one active script per product. Deactivate a script to hide it from telecallers.">
      <TelecallerScriptsPanel />
    </TelecallerCataloguePage>
  );
}
