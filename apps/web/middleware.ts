import { NextRequest, NextResponse } from "next/server";
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  const protectedRoute = p!=="/admin/login" && /^\/(it\/(student|trainer|placement|hr|admin)|overseas\/(student|counselor|university|agent|admin)|admin)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    // AGN-008 QA8-07: `next` keeps the query string (e.g. an Applications filter); LoginForm only follows a same-origin path.
    const next=encodeURIComponent(p+req.nextUrl.search);
    if(p.startsWith("/admin")) return NextResponse.redirect(new URL(`/admin/login?next=${next}`,req.url));
    const division=p.startsWith("/overseas")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${next}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*"]};
