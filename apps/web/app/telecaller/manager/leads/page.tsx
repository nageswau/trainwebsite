import { TelecallerLeadsPage } from "@/components/TelecallerLeadPages";

// tel-008 (D5): a manager's leads -- direct reports' leads plus their teams' unassigned queue (T23).
export default function TeamLeadsPage() {
  return <TelecallerLeadsPage manager />;
}
