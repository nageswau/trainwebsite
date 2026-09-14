import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";

export default async function News() {
  let posts: any[] = [];
  try { posts = await publicApi<any[]>("/api/v1/public/posts"); } catch {}
  const items = posts.map(post => ({
    id: String(post.id), searchText: `${post.title} ${post.summary} ${post.division} ${post.category || ""}`,
    filters: {division: post.division, category: post.category || "Uncategorized"}, sortValues: {title: post.title, created: post.created_at},
    content: <article className="card"><span className="badge">{post.division}</span><h3 style={{marginTop: 12}}>{post.title}</h3><p className="muted">{post.summary}</p><Link className="btn small" href={`/news/${post.slug}`}>Read article</Link></article>,
  }));
  return <PublicShell><PageHero eyebrow="News & Insights" title="Latest News" description="Updates from EduSphere IT Training, placement activities, overseas education, university events and student opportunities."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="articles" searchPlaceholder="Search news and insights…" filters={[{key: "division", label: "Division"}, {key: "category", label: "Category"}]} sorts={[{value: "newest", key: "created", label: "Newest first", direction: "desc"}, {value: "oldest", key: "created", label: "Oldest first"}, {value: "title", key: "title", label: "Title A–Z"}]} empty={<div className="card"><h3>No published news yet</h3><p className="muted">Administrators can publish posts through the CMS.</p></div>}/></div></section></PublicShell>;
}
