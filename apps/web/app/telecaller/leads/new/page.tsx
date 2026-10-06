import { TelecallerNewLeadPage } from "@/components/TelecallerLeadPages";

// tel-005 (spec §4, I2): a telecaller enters a lead, which is assigned to them.
export default function NewLeadPage() {
  return <TelecallerNewLeadPage manager={false} />;
}
