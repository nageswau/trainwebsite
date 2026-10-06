import PortalPage from "@/components/PortalPage";
export default async function Page({params,searchParams}:{params:Promise<{section:string}>;searchParams:Promise<Record<string,string|string[]|undefined>>}){const{section}=await params;return <PortalPage division="overseas" role="counselor" section={section} query={await searchParams}/>}
