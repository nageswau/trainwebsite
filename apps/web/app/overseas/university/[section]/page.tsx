import PortalPage from "@/components/PortalPage";
export default async function Page({params}:{params:Promise<{section:string}>}){const{section}=await params;return <PortalPage division="overseas" role="university" section={section}/>}
