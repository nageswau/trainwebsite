import PortalPage from "@/components/PortalPage";
// itc-030 (DEC-SCOPE-367): every IT counselor's dashboard for the IT Admin; the address carries the filters (owner included).
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){return <PortalPage division="it" role="admin" section="counselor-dashboard" query={await searchParams}/>}
