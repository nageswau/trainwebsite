import SiteHeader from "./SiteHeader";import Footer from "./Footer";
export default function PublicShell({children,division="corporate"}:{children:React.ReactNode;division?:"corporate"|"it"|"overseas"}){return <><a className="skip-link" href="#main-content">Skip to main content</a><SiteHeader division={division}/><main id="main-content" tabIndex={-1}>{children}</main><Footer/></>}
