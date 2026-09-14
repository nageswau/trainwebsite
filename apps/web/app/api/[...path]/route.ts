import { NextRequest, NextResponse } from "next/server";
const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
async function proxy(req:NextRequest, ctx:{params:Promise<{path:string[]}>}) {
  const {path} = await ctx.params;
  const target = new URL(`${backend}/api/${path.join("/")}`);
  req.nextUrl.searchParams.forEach((v,k)=>target.searchParams.append(k,v));
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("expect");
  const body = ["GET","HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  const upstream = await fetch(target, {method:req.method, headers, body, redirect:"manual"});
  const outHeaders = new Headers(upstream.headers);
  outHeaders.delete("content-encoding");
  outHeaders.delete("content-length");
  return new NextResponse(upstream.body, {status:upstream.status, headers:outHeaders});
}
export const GET=proxy; export const POST=proxy; export const PUT=proxy; export const PATCH=proxy; export const DELETE=proxy;
