import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import { publicApi } from "@/lib/api";
import type { CareerPath } from "@/lib/types";

export default async function CareerPaths() {
  let paths: CareerPath[] = [];
  try {
    paths = await publicApi<CareerPath[]>("/api/v1/public/career-paths?division=it");
  } catch {}

  const items = paths.map((path) => ({
    id: path.id,
    searchText: `${path.title} ${path.summary} ${path.skills.join(" ")}`,
    sortValues: { title: path.title },
    content: (
      <article className="card" key={path.id}>
        <h3>{path.title}</h3>
        <p className="muted">{path.summary}</p>
        <p style={{ fontSize: 13 }}>{path.skills.slice(0, 4).join(" · ")}</p>
        <Link className="btn small" href={`/it/career-paths/${path.slug}`}>View roadmap</Link>
      </article>
    ),
  }));

  return (
    <PublicShell division="it">
      <PageHero
        eyebrow="Career Paths"
        title="Plan a real technology career, not just a course"
        description="Each career path shows the skills, related programs, and realistic outcomes so you can choose the right roadmap before you enrol."
      />
      <section className="section">
        <div className="container">
          <CollectionExplorer
            items={items}
            noun="career paths"
            searchPlaceholder="Search career paths…"
            sorts={[{ value: "title", key: "title", label: "Title A–Z" }]}
            empty={
              <div className="card">
                <h3>No career paths published yet</h3>
                <p className="muted">Administrators can publish career paths through the CMS.</p>
              </div>
            }
          />
        </div>
      </section>
    </PublicShell>
  );
}
