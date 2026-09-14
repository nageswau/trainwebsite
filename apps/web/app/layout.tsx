import type { Metadata } from "next";
import "./globals.css";
import "./controls.css";
import Analytics from "@/components/Analytics";
export const metadata:Metadata={title:{default:"EduSphere | Empowering Careers. Building Global Opportunities.",template:"%s | EduSphere"},description:"EduSphere IT Training & Placement and Overseas Education services."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}<Analytics/></body></html>}
