import PortalPage from "@/components/PortalPage";
// hrc-002 (DEC-SCOPE-374 R3): the Interviewer's dashboard (assignments arrive with hrc-029).
export default function Page() {
  return <PortalPage division="it" role="interviewer" section="dashboard" />;
}
