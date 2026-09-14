import { NextRequest, NextResponse } from "next/server";
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  const protectedRoute = p!=="/admin/login" && /^\/(it\/(student|trainer|placement|hr|admin)|overseas\/(student|counselor|university|agent|admin)|admin)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    if(p.startsWith("/admin")) return NextResponse.redirect(new URL(`/admin/login?next=${encodeURIComponent(p)}`,req.url));
    const division=p.startsWith("/overseas")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${encodeURIComponent(p)}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*"]};
