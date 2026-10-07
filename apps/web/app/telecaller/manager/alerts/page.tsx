import TelecallerAlertSettingsPanel from "@/components/TelecallerAlertSettingsPanel";
import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";

// tel-020 (T14, AL1, AL11): each team's Lead Not Contacted and Hot Lead Pending thresholds.
export default function TelecallerManagerAlertsPage() {
  return (
    <TelecallerCataloguePage title="Alert settings" intro="Choose when telecallers are alerted about leads that are waiting. Each team has its own thresholds, in whole hours. Follow-up, appointment, assignment and return alerts are always on.">
      <TelecallerAlertSettingsPanel />
    </TelecallerCataloguePage>
  );
}
