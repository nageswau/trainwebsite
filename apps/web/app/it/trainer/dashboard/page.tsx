import PortalPage from "@/components/PortalPage";
// itc-024 (DEC-SCOPE-355 W5): the address carries the batch filter (`?batch=`).
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){return <PortalPage division="it" role="trainer" section="dashboard" query={await searchParams}/>}
