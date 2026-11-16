import type { Metadata } from "next";
import "./globals.css";
import "./controls.css";
import CookieConsent from "@/components/CookieConsent";
export const metadata:Metadata={title:{default:"EduSphere | Empowering Careers. Building Global Opportunities.",template:"%s | EduSphere"},description:"EduSphere IT Training & Placement and Overseas Education services."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}<CookieConsent gaId={process.env.NEXT_PUBLIC_GA_ID}/></body></html>}
