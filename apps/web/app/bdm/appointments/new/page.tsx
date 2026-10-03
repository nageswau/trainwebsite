import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import type { Organization } from "@/lib/bdmOrganizations";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: book an appointment. `?organization=<id>` (from the organization page) preselects it; an unknown, out-of-scope or archived
// organization is simply not preselected -- the API refuses archived ones with its own message (A4).
export default async function BdmAppointmentNewPage({ searchParams }: { searchParams: Promise<{ organization?: string }> }) {
  const { organization: orgParam } = await searchParams;
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  let organization: Organization | null = null;
  if (orgParam) {
    try {
      const found = (await serverApi<{ organization: Organization }>(`/api/v1/bdm/organizations/${encodeURIComponent(orgParam)}`)).organization;
      organization = found.assigned_bdm.id === me.id && !found.archived ? found : null;
    } catch (e) {
      if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, BDM_SIGN_IN);
    }
  }
  const type = me.bdm_profile.bdm_type;
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Appointments</div>
            <h2>Book appointment</h2>
            <p className="muted">Times are India time (IST). You can book for organizations assigned to you.</p>
          </div>
        </div>
        <div className="action-card wide">
          <BdmAppointmentForm mode="create" bdmType={type} initialOrganization={organization} />
        </div>
      </div>
    </PortalShell>
  );
}
