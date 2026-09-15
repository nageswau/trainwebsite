"use client";
import Link from "next/link"; import Image from "next/image"; import {useRouter} from "next/navigation"; import type {NavItem} from "@/lib/navigation"; import MobileNavToggle from "./MobileNavToggle";
// RESPONSIVE_RULES.md baseline rule (NFR-RESP-001, CONFIRMED_CURRENT): "Primary action
// always reachable without horizontal scroll... collapses behind a toggle" -- below
// 640px this sidebar used to become a fixed bottom bar with `.portal-nav{overflow:auto}`
// (horizontal scroll, no visible affordance that more items existed off-screen: a
// Trainer's own 9-item nav truncated mid-word at "Mate[rials]" with no scrollbar/fade
// hint). Confirmed directly against the running app (tester feedback 2026-09-04, WhatsApp,
// RAID.md I-15) before fixing. Replaced with the exact same toggle+dropdown pattern
// already proven for the public site's own mobile nav (MobileNavToggle, built for
// FRONTEND_ANALYSIS.md #4.1) instead of inventing a new interaction -- see globals.css's
// `@media(max-width:640px)` block for the CSS side of this swap.
export default function PortalShell({children,nav,roleLabel,userName,studentCode}:{children:React.ReactNode;nav:NavItem[];roleLabel:string;userName:string;studentCode?:string|null}){const router=useRouter();async function logout(){await fetch("/api/v1/auth/logout",{method:"POST"});router.push("/");router.refresh()}return <div className="portal"><aside className="sidebar"><Link href="/"><Image className="sidebar-logo logo-on-dark" src="/brand/logo-dark.png" width={420} height={140} alt="EduSphere"/></Link><div className="role-pill"><strong>{roleLabel}</strong><br/>{userName}{studentCode&&<><br/><span style={{fontSize:12,opacity:0.85}}>Student ID: {studentCode}</span></>}</div><nav className="portal-nav">{nav.map(x=><Link key={x.href} href={x.href}>{x.label}</Link>)}</nav><div className="sidebar-footer"><button className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} onClick={logout}>Sign out</button></div></aside><main className="portal-main"><div className="portal-topbar"><strong>EduSphere Portal</strong><div style={{display:"flex",alignItems:"center",gap:12}}><span className="muted">{userName}</span><MobileNavToggle nav={nav} buttonClassName="portal-mobile-menu" panelClassName="portal-mobile-nav-panel" panelId="portal-mobile-nav-panel"/></div></div>{children}</main></div>}
