import { NextRequest, NextResponse } from "next/server";
const PUBLIC_PATHS = new Set(["/admin/login", "/admin/forgot-password", "/admin/reset-password", "/bdm/sign-in", "/telecaller/sign-in"]);
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  // bdm-001 (AC12): /bdm is protected; /bdm/sign-in is the public chooser. QA-05: the admin portal's recovery pages are public too.
  // tel-001 (AC5, TL1): /telecaller likewise, with /telecaller/sign-in as its chooser.
  // tel-017: an IT counselor's workspace is /it/counselor.
  // upc-001 (PU1): /partnership too -- heads under /partnership/head sign in at /admin, managers at /overseas.
  const protectedRoute = !PUBLIC_PATHS.has(p) &&/^\/(it\/(student|trainer|placement|hr|admin|counselor)|overseas\/(student|counselor|university|agent|admin)|admin|bdm|telecaller|partnership)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    // AGN-008 QA8-07: `next` keeps the query string (e.g. an Applications filter); LoginForm only follows a same-origin path.
    const next=encodeURIComponent(p+req.nextUrl.search);
    // bdm-001 / tel-001: managers (division global) sign in at /admin; a BDM's or telecaller's portal depends on their module/team,
    // so they pick on their chooser.
    if(p.startsWith("/admin")||/^\/((bdm|telecaller)\/manager|partnership\/head)(\/|$)/.test(p)) return NextResponse.redirect(new URL(`/admin/login?next=${next}`,req.url));
    if(p.startsWith("/bdm")) return NextResponse.redirect(new URL(`/bdm/sign-in?next=${next}`,req.url));
    if(p.startsWith("/telecaller")) return NextResponse.redirect(new URL(`/telecaller/sign-in?next=${next}`,req.url));
    const division=p.startsWith("/overseas")||p.startsWith("/partnership")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${next}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*","/bdm/:path*","/telecaller/:path*","/partnership/:path*"]};
