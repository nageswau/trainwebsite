import PortalPage from "@/components/PortalPage";
// nehn-038 (DEC-SCOPE-306): the query carries the dashboard's referral-date range (?from=&to=).
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){return <PortalPage division="overseas" role="agent" section="dashboard" query={await searchParams}/>}
