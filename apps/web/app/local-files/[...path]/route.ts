import { NextRequest, NextResponse } from "next/server";
const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
async function proxy(req:NextRequest, ctx:{params:Promise<{path:string[]}>}) {
  const {path} = await ctx.params;
  const target = new URL(`${backend}/local-files/${path.join("/")}`);
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("expect");
  const upstream = await fetch(target, {method:"GET", headers, redirect:"manual"});
  const outHeaders = new Headers(upstream.headers);
  outHeaders.delete("content-encoding");
  outHeaders.delete("content-length");
  return new NextResponse(upstream.body, {status:upstream.status, headers:outHeaders});
}
export const GET=proxy;
