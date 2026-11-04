import PortalPage from "@/components/PortalPage";
// hrc-002 (DEC-SCOPE-374 R3): the HR Manager's read-only recruitment oversight.
export default function Page() {
  return <PortalPage division="it" role="hr-manager" section="dashboard" />;
}
