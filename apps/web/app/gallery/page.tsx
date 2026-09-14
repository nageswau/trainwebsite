import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";

export default async function Gallery() {
  let gallery: any[] = [];
  try { gallery = await publicApi<any[]>("/api/v1/public/gallery"); } catch {}
  const items = gallery.map(item => ({
    id: String(item.id), searchText: `${item.title} ${item.alt_text || ""} ${item.category || ""} ${item.division || ""}`,
    filters: {category: item.category || "General", division: item.division || "General"}, sortValues: {title: item.title, category: item.category},
    content: <figure className="card"><div style={{height: 180, borderRadius: 12, background: "#eaf1fb", display: "grid", placeItems: "center", overflow: "hidden"}}>{item.image_url?.startsWith("http") ? <img src={item.image_url} alt={item.alt_text}/> : <span className="muted">Production media: {item.title}</span>}</div><figcaption style={{marginTop: 14}}><span className="badge">{item.category}</span><h3 style={{marginTop: 10}}>{item.title}</h3></figcaption></figure>,
  }));
  return <PublicShell><PageHero eyebrow="Gallery" title="EduSphere Gallery" description="Training, events, education fairs, webinars and student activities managed from the CMS."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="gallery items" searchPlaceholder="Search gallery…" filters={[{key: "category", label: "Category"}, {key: "division", label: "Division"}]} sorts={[{value: "title", key: "title", label: "Title A–Z"}, {value: "title-desc", key: "title", label: "Title Z–A", direction: "desc"}, {value: "category", key: "category", label: "Category A–Z"}]} empty={<div className="card"><h3>Gallery content is CMS-managed</h3><p className="muted">Upload approved images through the Admin panel after production S3 storage is configured.</p></div>}/></div></section></PublicShell>;
}
