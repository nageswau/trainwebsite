import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerTemplatesPanel from "@/components/TelecallerTemplatesPanel";

// tel-012 (EVID-019 §11, §12; T9): WhatsApp and email message templates.
export default function TelecallerManagerTemplatesPage() {
  return (
    <TelecallerCataloguePage title="Message templates" intro="WhatsApp and email messages telecallers start from. They can edit the text before sending. Use placeholders for the lead's details; attach a brochure to use {brochure_link}.">
      <TelecallerTemplatesPanel />
    </TelecallerCataloguePage>
  );
}
