import { accessUnavailable } from "@/components/AccessUnavailable";
import EnrolExistingBody from "@/components/EnrolExistingBody";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";
import { telecallerNav } from "@/lib/telecallerNav";

// ENH-033 (DEC-SCOPE-441 D1): a telecaller adds their own division to an existing student of the other one.
export default async function TelecallerEnrolExistingPage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  const division = me.division === "it" ? "it" : "overseas";
  return (
    <PortalShell nav={await telecallerNav()} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <EnrolExistingBody division={division} />
    </PortalShell>
  );
}
