import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerBrochuresPanel from "@/components/TelecallerBrochuresPanel";

// tel-012 (T9, C1): brochure and fee-sheet PDFs that leads open from a 7-day link.
export default function TelecallerManagerBrochuresPage() {
  return (
    <TelecallerCataloguePage title="Brochures" intro="PDF brochures and fee sheets. A lead opens one from a link that works without signing in for 7 days. Deactivating a brochure stops all of its links at once.">
      <TelecallerBrochuresPanel />
    </TelecallerCataloguePage>
  );
}
