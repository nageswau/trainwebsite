import Link from "next/link";
import Image from "next/image";
import { IT_PUBLIC, OVERSEAS_PUBLIC } from "@/lib/navigation";
import HeaderAuthActions from "./HeaderAuthActions";
import MobileNavToggle from "./MobileNavToggle";
import DesktopNav from "./DesktopNav";
export default function SiteHeader({division="corporate"}:{division?:"corporate"|"it"|"overseas"}){
 const nav=division==="it"?IT_PUBLIC:division==="overseas"?OVERSEAS_PUBLIC:[{label:"IT Training",href:"/it"},{label:"Overseas Education",href:"/overseas"},{label:"FAQ",href:"/faq"},{label:"Contact",href:"/contact"}];
 const loginHref=division==="overseas"?"/overseas/login":"/it/login";
 return <>
  <div className="division-bar"><div className="container division-row"><span>EduSphere · Learn, Apply, Succeed</span><div className="division-links"><Link className={division==="it"?"active":""} href="/it">IT Training & Placement</Link><Link className={division==="overseas"?"active":""} href="/overseas">Overseas Education</Link></div></div></div>
  <header className="site-header"><div className="container header-row"><Link href="/"><Image className="brand-logo" src="/brand/logo-light.png" width={420} height={140} alt="EduSphere" priority/></Link><DesktopNav nav={nav}/><MobileNavToggle nav={nav}/><div className="header-actions"><Link className="btn secondary" href={division==="overseas"?"/overseas/contact":"/it/contact"}>Enquire</Link><HeaderAuthActions loginHref={loginHref}/></div></div></header>
 </>
}
