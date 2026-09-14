import Image from "next/image";import Link from "next/link";import LoginForm from "@/components/LoginForm";
// Demo-accounts box is dev-only -- ENVIRONMENT is a server-only var (docker-compose.yml's
// web service), never NEXT_PUBLIC_, and defaults to "production" if ever unset, so an
// unconfigured deploy fails safe (hidden) rather than leaking real-looking credentials on
// a public login page. This page in particular advertises the super_admin login -- the
// single most sensitive account on the whole platform. `dynamic = "force-dynamic"` is
// required here, not optional: this route has no other dynamic data, so Next.js would
// otherwise prerender it once at build time and bake in whatever ENVIRONMENT happened to
// be set then -- a later runtime override (e.g. deploying the same image to prod with
// ENVIRONMENT=production) would silently have no effect and the demo box would ship to
// production anyway. Confirmed by reproducing that exact failure before adding this line.
export const dynamic = "force-dynamic";
export default function AdminLogin(){const showDemoAccounts=process.env.ENVIRONMENT!=="production";return <div className="auth-page"><div className="auth-brand"><div className="auth-brand-inner"><Image className="logo-on-dark" src="/brand/logo-dark.png" alt="EduSphere" width={520} height={180}/><div className="eyebrow">Central Administration</div><h1 style={{fontSize:46}}>One governance layer. Independent operations.</h1><p className="lead">The Super Admin can govern both divisions while IT and Overseas administrators remain restricted to their own business data.</p></div></div><div className="auth-form-wrap"><div className="auth-card"><Link href="/" className="muted">← Corporate website</Link><h2 style={{marginTop:22}}>Super Admin Login</h2><p className="muted">Restricted administrative access.</p><LoginForm division="global"/>{showDemoAccounts && <div className="card soft" style={{marginTop:18,padding:14}}><strong>Demo super admin</strong><p className="muted" style={{fontSize:12}}>superadmin@edusphere.local<br/>Password: Demo@123</p></div>}</div></div></div>}
