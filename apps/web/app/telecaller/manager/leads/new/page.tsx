import { TelecallerNewLeadPage } from "@/components/TelecallerLeadPages";

// tel-005 (spec §4, I2): a manager enters a lead, which tel-007 distributes (I6) or leaves in the team's unassigned queue.
export default function NewTeamLeadPage() {
  return <TelecallerNewLeadPage manager />;
}
