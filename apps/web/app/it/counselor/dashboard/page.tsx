import PortalPage from "@/components/PortalPage";
// itc-030 (DEC-SCOPE-367): the address carries the dashboard filters (course, batch, status, from, to).
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){return <PortalPage division="it" role="counselor" section="dashboard" query={await searchParams}/>}
