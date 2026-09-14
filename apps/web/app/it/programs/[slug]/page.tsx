import Link from "next/link";import PublicShell from "@/components/PublicShell";import {publicApi} from "@/lib/api";import type {Program} from "@/lib/types";import type {Metadata} from "next";

async function loadProgram(slug: string): Promise<Program | null> {
  try { return await publicApi<Program>(`/api/v1/public/programs/${slug}`); } catch { return null; }
}

// PUB-003's own stated requirement is "SEO" -- the list page already had static
// metadata, but no detail page anywhere in the app generates per-item metadata yet.
// Fixed here for programs specifically, since that's this feature's scope.
export async function generateMetadata({params}:{params:Promise<{slug:string}>}): Promise<Metadata> {
  const {slug} = await params;
  const p = await loadProgram(slug);
  if (!p) return {title: "Program not found"};
  return {title: p.title, description: p.summary};
}

export default async function ProgramDetail({params}:{params:Promise<{slug:string}>}){const{slug}=await params;const p=await loadProgram(slug);if(!p)return <PublicShell division="it"><section className="section"><div className="container"><h1>Program unavailable</h1><Link className="btn" href="/it/programs">Back to programs</Link></div></section></PublicShell>;return <PublicShell division="it"><section className="page-hero"><div className="container"><div className="breadcrumbs">IT Training / Programs / {p.title}</div><span className="badge">{p.category}</span><h1>{p.title}</h1><p className="lead">{p.summary}</p><div className="actions"><Link className="btn" href={`/it/contact?program=${p.slug}`}>Enquire about next batch</Link><Link className="btn secondary" href="/it/login">Student portal</Link></div></div></section><section className="section"><div className="container grid two"><div><h2>Curriculum</h2><ol>{p.curriculum.map(x=><li key={x} style={{padding:"8px 0"}}>{x}</li>)}</ol><h2 style={{marginTop:36}}>Placement Assistance</h2><p className="lead">{p.placement_assistance}</p></div><aside className="card"><h3>Program information</h3><ul className="list-clean"><li><strong>Duration</strong><span style={{float:"right"}}>{p.duration}</span></li><li><strong>Fees</strong><span style={{float:"right"}}>₹{Number(p.fees).toLocaleString("en-IN")}</span></li><li><strong>Certification</strong><br/><span className="muted">{p.certification}</span></li><li><strong>Trainer</strong><br/><span className="muted">{p.trainer_name}</span></li><li><strong>Eligibility</strong><br/><span className="muted">{p.eligibility}</span></li></ul></aside></div></section></PublicShell>}
