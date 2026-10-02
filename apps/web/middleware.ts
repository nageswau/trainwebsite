import { NextRequest, NextResponse } from "next/server";
const PUBLIC_PATHS = new Set(["/admin/login", "/admin/forgot-password", "/admin/reset-password", "/bdm/sign-in"]);
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  // bdm-001 (AC12): /bdm is protected; /bdm/sign-in is the public chooser. QA-05: the admin portal's recovery pages are public too.
  const protectedRoute = !PUBLIC_PATHS.has(p) &&/^\/(it\/(student|trainer|placement|hr|admin)|overseas\/(student|counselor|university|agent|admin)|admin|bdm)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    // AGN-008 QA8-07: `next` keeps the query string (e.g. an Applications filter); LoginForm only follows a same-origin path.
    const next=encodeURIComponent(p+req.nextUrl.search);
    // bdm-001: managers (division global) sign in at /admin; a BDM's portal depends on their type, so they pick on /bdm/sign-in.
    if(p.startsWith("/admin")||/^\/bdm\/manager(\/|$)/.test(p)) return NextResponse.redirect(new URL(`/admin/login?next=${next}`,req.url));
    if(p.startsWith("/bdm")) return NextResponse.redirect(new URL(`/bdm/sign-in?next=${next}`,req.url));
    const division=p.startsWith("/overseas")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${next}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*","/bdm/:path*"]};
