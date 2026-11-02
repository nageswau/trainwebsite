import LostReasonsPanel from "@/components/LostReasonsPanel";
import TelecallerCataloguePage from "@/components/TelecallerCataloguePage";
import { OBJECTIONS_URL } from "@/lib/leadCounseling";

// itc-010 (DEC-SCOPE-343 C6): the objections an IT counselor picks when recording a counseling session.
export default function TelecallerManagerCounselingObjectionsPage() {
  return (
    <TelecallerCataloguePage title="Counseling objections" intro="The objections an IT counselor ticks when recording a counseling session. Deactivate one to hide it from the form — sessions that already list it keep it.">
      <LostReasonsPanel list={{ url: OBJECTIONS_URL, singular: "objection", plural: "objections", empty: "No objections yet. Counselors can still describe objections in their own words." }} />
    </TelecallerCataloguePage>
  );
}
