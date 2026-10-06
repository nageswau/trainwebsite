import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import TelecallerProductsPanel from "@/components/TelecallerProductsPanel";

// tel-002 (T17/T18): the product/interest catalogue a lead's interest is chosen from.
export default function TelecallerManagerProductsPage() {
  return (
    <TelecallerCataloguePage title="Products" intro="The interests a telecaller can choose for a lead. IT and Overseas products go to their own team; choose the team for each Other product. Deactivate a product to hide it from pickers — leads and campaigns that use it keep it.">
      <TelecallerProductsPanel />
    </TelecallerCataloguePage>
  );
}
