import Image from "next/image";import Link from "next/link";import LoginForm from "@/components/LoginForm";
// Demo-accounts box is dev-only -- ENVIRONMENT is a server-only var (docker-compose.yml's
// web service), never NEXT_PUBLIC_, and defaults to "production" if ever unset, so an
// unconfigured deploy fails safe (hidden) rather than leaking real-looking credentials on
// a public login page. `dynamic = "force-dynamic"` is required here, not optional: this
// route has no other dynamic data, so Next.js would otherwise prerender it once at build
// time and bake in whatever ENVIRONMENT happened to be set then -- a later runtime
// override (e.g. deploying the same image to prod with ENVIRONMENT=production) would
// silently have no effect and the demo box would ship to production anyway. Confirmed by
// reproducing that exact failure before adding this line.
export const dynamic = "force-dynamic";
export default function ITLogin(){const showDemoAccounts=process.env.ENVIRONMENT!=="production";return <div className="auth-page"><div className="auth-brand"><div className="auth-brand-inner"><Image className="logo-on-dark" src="/brand/logo-dark.png" alt="EduSphere" width={520} height={180}/><div className="eyebrow">IT Training Portal</div><h1 style={{fontSize:46}}>Learn. Build. Get career-ready.</h1><p className="lead">Dashboards for students, trainers, placement teams, employers, and administrators.</p></div></div><div className="auth-form-wrap"><div className="auth-card"><Link href="/it" className="muted">← Back to IT Training</Link><h2 style={{marginTop:22}}>IT Training Portal</h2><p className="muted">Sign in with your authorised EduSphere IT account.</p><LoginForm division="it"/><p className="muted" style={{marginTop:18}}>New student? <Link href="/it/register" style={{color:"var(--blue)",fontWeight:800}}>Create an account</Link></p>{showDemoAccounts && <div className="card soft" style={{marginTop:18,padding:14}}><strong>Demo accounts</strong><p className="muted" style={{fontSize:12}}>student.it@edusphere.local · trainer@edusphere.local · placement@edusphere.local · hr@edusphere.local · itadmin@edusphere.local<br/>Password: Demo@123</p></div>}</div></div></div>}
