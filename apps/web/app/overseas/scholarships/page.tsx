import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";

export default async function Scholarships() {
  let scholarships: any[] = [];
  try { scholarships = await publicApi<any[]>("/api/v1/public/scholarships"); } catch {}
  const items = scholarships.map(scholarship => {
    const deadline = scholarship.deadline ? String(scholarship.deadline) : "";
    return {
      id: String(scholarship.id), searchText: `${scholarship.title} ${scholarship.amount} ${scholarship.eligibility} ${deadline}`,
      filters: {deadline: deadline ? deadline.slice(0, 4) : "Open-ended"}, sortValues: {title: scholarship.title, deadline},
      content: <div className="card"><span className="badge">Scholarship</span><h3 style={{marginTop: 12}}>{scholarship.title}</h3><p>{scholarship.amount}</p><p className="muted">{scholarship.eligibility}</p><p><strong>Deadline:</strong> {deadline ? new Date(deadline).toLocaleDateString("en-GB") : "Check current availability"}</p><a className="btn small" href="/overseas/login">Sign in to apply</a></div>,
    };
  });
  return <PublicShell division="overseas"><PageHero eyebrow="Scholarship Portal" title="Available Scholarships" description="Discover scholarship examples, review eligibility, then sign in to track scholarship applications."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="scholarships" searchPlaceholder="Search scholarship, amount, or eligibility…" filters={[{key: "deadline", label: "Deadline year"}]} sorts={[{value: "deadline", key: "deadline", label: "Deadline: soonest"}, {value: "deadline-desc", key: "deadline", label: "Deadline: latest", direction: "desc"}, {value: "title", key: "title", label: "Title A–Z"}]} empty={<div className="card"><h3>No scholarships available</h3><p className="muted">Published funding opportunities will appear here.</p></div>}/></div></section></PublicShell>;
}
