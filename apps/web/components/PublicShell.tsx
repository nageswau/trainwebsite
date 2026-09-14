import SiteHeader from "./SiteHeader";import Footer from "./Footer";
export default function PublicShell({children,division="corporate"}:{children:React.ReactNode;division?:"corporate"|"it"|"overseas"}){return <><SiteHeader division={division}/><main>{children}</main><Footer/></>}
